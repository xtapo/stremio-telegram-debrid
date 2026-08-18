"""
Catalog, meta and id-mapping layer for the MoviesDrive addon.

Everything here is served through moviesdrive_perf.cached_call, which gives:

* single flight - ten viewers opening the same page cause one scrape
* stale-while-revalidate - an expired catalog is returned instantly and
  refreshed in the background, so nobody ever waits for a scrape
* negative caching - a miss is remembered for a minute instead of rescraping
* disk persistence - a restart keeps the imdb and cinemeta mappings

The scraping itself is defensive: card selectors, category slugs, the genre map
and the search endpoint are all overridable from the environment, the real
items-per-page value is learned from the site instead of assumed, and a page
that parses to zero items says so in the log instead of silently returning an
empty catalog.
"""

import asyncio
import json
import logging
import os
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

import moviesdrive_perf as perf
from moviesdrive_perf import (
    NEGATIVE_TTL,
    cached_call,
    make_soup,
    race_fetch_text,
)
import moviesdrive_resolver as resolver
from moviesdrive_resolver import (
    ALL_BASES,
    MOVIESDRIVE_BASE_URL,
    absolute,
    current_base,
    fetch_html,
    looks_like_series,
    post_content,
    request_headers,
    strip_base,
)

logger = logging.getLogger("moviesdrive_addon")

CINEMETA_BASE = "https://v3-cinemeta.strem.io"
CINEMETA_API = CINEMETA_BASE + "/meta"
CINEMETA_CATALOG = CINEMETA_BASE + "/catalog"
OPENSUBTITLES_BASE = "https://opensubtitles-v3.strem.io/subtitles/"

CATALOG_TTL = perf._env_int("MD_CATALOG_TTL", 300)
CATALOG_STALE_TTL = perf._env_int("MD_CATALOG_STALE_TTL", 1800)
SEARCH_TTL = perf._env_int("MD_SEARCH_TTL", 600)
META_TTL = perf._env_int("MD_META_TTL", 900)
META_STALE_TTL = perf._env_int("MD_META_STALE_TTL", 7200)
CINEMETA_TTL = perf._env_int("MD_CINEMETA_TTL", 3600)
IMDB_TTL = perf._env_int("MD_IMDB_TTL", 86400)
SUBS_TTL = perf._env_int("MD_SUBS_TTL", 900)
MD_ITEMS_PER_PAGE = perf._env_int("MD_ITEMS_PER_PAGE", 24)
CATALOG_BATCH_SIZE = perf._env_int("MD_CATALOG_PAGE_SIZE", 20)
META_ENRICH_TIMEOUT = perf._env_float("MD_META_ENRICH_TIMEOUT", 6.0)
META_ENRICH_COUNT = perf._env_int("MD_META_ENRICH_COUNT", 8)
# 0 disables the guess entirely; the old code invented 12 episodes.
FALLBACK_EPISODES = perf._env_int("MD_FALLBACK_EPISODES", 1)

# Paths and slugs: the source renames these more often than anything else.
CATEGORY_PREFIX = os.getenv("MD_CATEGORY_PREFIX") or "/category/"
CATEGORY_MOVIES = (os.getenv("MD_CATEGORY_MOVIES") or "movies").strip("/")
CATEGORY_SERIES = (os.getenv("MD_CATEGORY_SERIES") or "web").strip("/")
CATEGORY_4K = (os.getenv("MD_CATEGORY_4K") or "2160p-4k").strip("/")
SEARCH_PATH = os.getenv("MD_SEARCH_PATH") or "/search.php?q={query}&page={page}"
SEARCH_HTML_PATH = os.getenv("MD_SEARCH_HTML_PATH") or "/page/{page}/?s={query}"

DEFAULT_CATEGORIES_MAP = {
    "Action": "action",
    "Adventure": "adventure",
    "Animation": "animation",
    "Anime": "anime",
    "Bollywood": "bollywood",
    "Comedy": "comedy",
    "Crime": "crime",
    "Documentary": "documentary",
    "Drama": "drama",
    "Dual Audio": "dual-audio",
    "DV HDR": "dv-hdr",
    "Family": "family",
    "Fantasy": "fantasy",
    "Hindi Dubbed": "hindi-dubbed",
    "Hollywood": "hollywood",
    "Horror": "horror",
    "IMAX": "imax",
    "K Drama": "k-drama",
    "Mystery": "mystery",
    "Netflix": "netflix",
    "Romance": "romance",
    # The source really does misspell these two slugs.
    "Sci-Fi": "sifi",
    "South": "south",
    "Thriller": "triller",
    "War": "war",
    "2160p 4K": "2160p-4k",
}


def _load_categories_map() -> Dict[str, str]:
    """MD_GENRE_MAP is a JSON object of {\"Genre\": \"slug\"} overrides."""
    mapping = dict(DEFAULT_CATEGORIES_MAP)
    raw = (os.getenv("MD_GENRE_MAP") or "").strip()
    if not raw:
        return mapping
    try:
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("MD_GENRE_MAP is not valid JSON, ignoring it: %s", exc)
        return mapping
    if isinstance(data, dict):
        mapping.update({str(k): str(v).strip("/") for k, v in data.items() if v})
    return mapping


CATEGORIES_MAP = _load_categories_map()
CATEGORIES_MAP["2160p 4K"] = CATEGORY_4K
GENRE_OPTIONS = list(CATEGORIES_MAP.keys())

# Card selectors, tried in order. The first one that yields items wins.
CARD_SELECTORS = perf._env_list("MD_CARD_SELECTORS") or [
    "div.poster-card",
    "article",
    "li.post-item",
    "div.post-card",
    "div[class*='poster']",
    "div[class*='movie-card']",
    "div[class*='post-thumb']",
]
# Last resort: the anchors WordPress themes use for post titles.
LINK_SELECTORS = perf._env_list("MD_LINK_SELECTORS") or [
    "h2.entry-title a[href]",
    "h3.entry-title a[href]",
    "h2.title a[href]",
    ".recent-posts a[href]",
    "a[rel='bookmark']",
]

SKIP_SLUG_WORDS = ("category", "tag", "contact", "dmca", "privacy")
NOISE_WORDS = (
    "web-dl", "hindi", "dd5-1", "english", "480p", "720p", "1080p",
    "2160p", "4k", "sdr", "x264", "esubs", "full-movie", "esub",
)

# Learned from the site on the first catalog page (see _note_page_size).
_OBSERVED_ITEMS_PER_PAGE: Optional[int] = None


def _fill_path(template: str, query: str, page: int) -> str:
    return template.replace("{query}", urllib.parse.quote(query)).replace(
        "{page}", str(page)
    )


def _items_per_page() -> int:
    return _OBSERVED_ITEMS_PER_PAGE or MD_ITEMS_PER_PAGE


def _note_page_size(count: int) -> None:
    """Learn the real page size from a full first page."""
    global _OBSERVED_ITEMS_PER_PAGE
    if count < max(CATALOG_BATCH_SIZE, 6) or count == _OBSERVED_ITEMS_PER_PAGE:
        return
    _OBSERVED_ITEMS_PER_PAGE = count
    if count != MD_ITEMS_PER_PAGE:
        logger.info(
            "MoviesDrive serves %s items per page (MD_ITEMS_PER_PAGE=%s), "
            "using the observed value for pagination",
            count,
            MD_ITEMS_PER_PAGE,
        )


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------
def _search_urls(path: str) -> List[str]:
    urls = [current_base() + path]
    for base in perf.candidate_bases(MOVIESDRIVE_BASE_URL, extra=ALL_BASES, limit=4):
        candidate = base.rstrip("/") + path
        if candidate not in urls:
            urls.append(candidate)
    return urls


async def _search_json(query: str, page: int) -> Optional[Dict[str, Any]]:
    path = _fill_path(SEARCH_PATH, query, page)
    headers = request_headers(current_base() + "/search.html")
    headers["Accept"] = "application/json"
    text, _final_url = await race_fetch_text(_search_urls(path), headers=headers)
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        logger.info(
            "MoviesDrive search endpoint did not answer JSON for %r "
            "(%s bytes, starts with %r), trying the HTML search page",
            query,
            len(text),
            text[:60],
        )
        return None
    if isinstance(data, dict) and data.get("hits"):
        return data
    if isinstance(data, list) and data:
        return {"hits": data, "found": len(data)}
    return None


async def _search_html(query: str, page: int) -> Optional[Dict[str, Any]]:
    """Fallback for when /search.php stops returning Typesense-style JSON.

    Without this, every tt* id coming from Cinemeta ends up with zero streams,
    because stream_endpoint depends entirely on the search step.
    """
    path = _fill_path(SEARCH_HTML_PATH, query, page)
    html_text = await fetch_html(current_base() + path)
    if not html_text:
        return None
    items = _parse_cards(html_text)
    if not items:
        logger.warning("MoviesDrive HTML search parsed 0 results for %r", query)
        return None
    for item in items:
        item["genres"] = ["MoviesDrive", "Tìm kiếm"]
    logger.info("MoviesDrive HTML search returned %s results for %r", len(items), query)
    return {"hits": [], "found": len(items), "items": items}


async def _search_request(query: str, page: int) -> Optional[Dict[str, Any]]:
    data = await _search_json(query, page)
    if data:
        return data
    return await _search_html(query, page)


async def search_moviesdrive_api(query: str, page: int = 1) -> Dict[str, Any]:
    data = await cached_call(
        "search:" + query + ":" + str(page),
        lambda: _search_request(query, page),
        ttl=SEARCH_TTL,
        stale_ttl=CATALOG_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )
    return data or {"hits": [], "found": 0}


# ------------------------------------------------------------------
# Catalog
# ------------------------------------------------------------------
def _category_url(slug: str, page: int) -> str:
    prefix = CATEGORY_PREFIX if CATEGORY_PREFIX.startswith("/") else "/" + CATEGORY_PREFIX
    if not prefix.endswith("/"):
        prefix += "/"
    url = current_base() + prefix + slug.strip("/") + "/"
    if page > 1:
        url = url + "page/" + str(page) + "/"
    return url


def _catalog_url(cat_type: str, cat_id: str, genre: Optional[str], page: int) -> str:
    if cat_id == "moviesdrive_movies_4k":
        slug = CATEGORY_4K
    elif genre and genre in CATEGORIES_MAP:
        slug = CATEGORIES_MAP[genre]
    elif cat_type == "series" or cat_id == "moviesdrive_series_latest":
        slug = CATEGORY_SERIES
    else:
        slug = CATEGORY_MOVIES
    return _category_url(slug, page)


def _extract_img_src(img_tag) -> str:
    if not img_tag:
        return ""
    src = (
        img_tag.get("data-lazy-src")
        or img_tag.get("data-src")
        or img_tag.get("data-original")
        or img_tag.get("src")
        or ""
    )
    if not src or src.startswith("data:"):
        srcset = img_tag.get("srcset") or img_tag.get("data-srcset") or ""
        if srcset:
            src = srcset.split(",")[0].strip().split(" ")[0]
    return src.strip()


def _is_noise_image(src: str) -> bool:
    if not src or src.startswith("data:"):
        return True
    s = src.lower()
    return any(
        bad in s
        for bad in (
            "log.png", "logo", "telegram", "/t.jpg", "join",
            "banner", "screenshot", "imgshare", "default-poster",
            "search", "icon"
        )
    )


def _extract_meta_poster(soup) -> str:
    post = soup.find(
        "div",
        class_=lambda c: c and any(
            k in c for k in ("post-layout", "entry-content", "thecontent", "post-content", "post-body")
        ),
    ) or soup

    candidates = []
    for img in post.find_all("img"):
        src = _extract_img_src(img)
        if _is_noise_image(src):
            continue
        src_lower = src.lower()
        alt = (img.get("alt") or "").lower()
        if (
            "poster" in alt
            or "cover" in alt
            or any(d in src_lower for d in ("tmdb.org", "media-amazon.com", "m.media-amazon.com", "imdb.com", "fanart.tv"))
        ):
            return absolute(src)
        candidates.append(src)

    if candidates:
        return absolute(candidates[0])
    return ""


def clean_title(title: str) -> str:
    t = title or ""
    # Strip any leading non-alphanumeric unicode icons
    t = re.sub(r"^[^\w\s]+", "", t).strip()
    # Remove leading Download / Watch
    t = re.sub(r"^(?:Download|Watch)\s+", "", t, flags=re.I)
    # Remove quality / codec / channel / episode / platform noise tags in brackets
    t = re.sub(
        r"[\(\[\{]\s*(?:WEB-DL|WEBRip|BluRay|HDTC|DS4K|4K|1080p|720p|480p|2160p|HEVC|10Bit|x264|x265|Dual Audio|Hindi|English|Tamil|Telugu|Punjabi|ESubs?|Multi Audio|Full Movie|ALL Episodes|NF Series|AMZN-Series|PrimeVideo Series|Amazon Original|Disney\+|Hotstar|SonyLIV|Zee5|JioHotstar|Anime Movie|HD x264|In English)[^\)\]\}]*[\)\]\}]",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"\b(?:Disney\+\s*Hotstar|Disney\+|Hotstar|Netflix|Amazon Original|PrimeVideo|SonyLIV|Zee5|JioHotstar|JioCinema|Full Movie)\b",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"\b(?:WEB-DL|WEBRip|BluRay|HDTC|DS4K|4K|1080p|720p|480p|2160p|HEVC|10Bit|x264|x265|Dual Audio|Hindi|English|Tamil|Telugu|Punjabi|ESubs?|Multi Audio|Full Movie|ALL Episodes|NF Series|AMZN-Series|PrimeVideo Series)\b.*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"[\–\-\|]\s*(?:MoviesDrive|Dual Audio|Hindi|English|480p|720p|1080p|2160p|4K|Full Movie|Disney\+|Hotstar|AMZN|Amazon).*", "", t, flags=re.I)
    t = re.sub(r"[\[\]\(\)\|\-–—]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _usable_slug(slug: str) -> bool:
    if not slug or len(slug) < 4:
        return False
    low = slug.lower()
    if any(word in low for word in SKIP_SLUG_WORDS):
        return False
    if low.startswith(("http", "#", "mailto:", "javascript:")):
        return False
    return "/" not in slug.strip("/") or low.count("/") <= 2


def _build_item(slug: str, title: str, thumb: str) -> Dict[str, Any]:
    cleaned_name = clean_title(title) or title

    year_match = re.search(r"\b(19\d\d|20\d\d)\b", title)
    year_str = year_match.group(1) if year_match else ""

    if re.search(r"\b(4k|2160p|uhd)\b", title, re.I):
        quality_str = "4K Ultra HD"
    elif re.search(r"\b(1080p|fhd)\b", title, re.I):
        quality_str = "1080p Full HD"
    elif re.search(r"\b(720p|hd)\b", title, re.I):
        quality_str = "720p HD"
    elif re.search(r"\b(480p|sd)\b", title, re.I):
        quality_str = "480p SD"
    else:
        quality_str = "1080p Full HD"

    audio_match = re.search(
        r"\[([^\]]*(?:Hindi|English|Tamil|Telugu|Kannada|Malayalam|Dual|Multi)[^\]]*)\]",
        title,
        re.I,
    )
    audio_str = audio_match.group(1).strip() if audio_match else "Dual Audio"

    desc_badge_parts = []
    if year_str:
        desc_badge_parts.append(f"📅 Năm: {year_str}")
    if quality_str:
        desc_badge_parts.append(f"📺 {quality_str}")

    desc_lines = []
    if desc_badge_parts:
        desc_lines.append(" | ".join(desc_badge_parts))
    desc_lines.append(f"🔊 Âm thanh: {audio_str}")
    desc_lines.append("🇻🇳 Phụ đề: Tiếng Việt tự động (AI Fast & Quality)")
    desc_lines.append("⚡ Máy chủ phát: Direct CDN 10Gbps")
    desc_lines.append(f"🎬 Xem phim {cleaned_name} chất lượng cao trên MoviesDrive.")

    poster_url = absolute(thumb)
    return {
        "id": "moviesdrive:" + slug,
        "type": "series" if looks_like_series(title) else "movie",
        "name": cleaned_name,
        "poster": poster_url,
        "posterShape": "poster",
        "background": poster_url,
        "releaseInfo": year_str,
        "description": "\n".join(desc_lines),
        "genres": ["MoviesDrive", "Phim Mới"],
    }


def _title_from_node(node, a_tag, img_tag, slug: str) -> str:
    title_el = node.find(
        ["p", "h2", "h3", "h4", "span"], class_=lambda c: c and "title" in c
    ) or node.find(["p", "h2", "h3", "h4"])
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        title = a_tag.get("title") or ""
    if not title and img_tag:
        title = img_tag.get("alt") or ""
    if not title:
        title = slug.replace("-", " ").title()
    return title


def _parse_cards(html_text: str) -> List[Dict[str, Any]]:
    """Parse a listing page into catalog items.

    The old version only accepted div.poster-card or <article>, so any theme
    change silently produced an empty catalog. Now several selectors are tried,
    then the post-title anchors, and the outcome is always logged.
    """
    soup = make_soup(html_text)
    items: List[Dict[str, Any]] = []
    seen = set()
    used = ""

    for selector in CARD_SELECTORS:
        try:
            nodes = soup.select(selector)
        except Exception:
            continue
        if not nodes:
            continue
        for node in nodes:
            a_tag = node.find_parent("a", href=True) or node.find("a", href=True)
            if not a_tag:
                continue
            slug = strip_base(a_tag["href"])
            if slug in seen or not _usable_slug(slug):
                continue
            seen.add(slug)
            img_tag = node.find("img")
            thumb = ""
            if img_tag:
                thumb = _extract_img_src(img_tag)
                if _is_noise_image(thumb):
                    thumb = ""
            items.append(
                _build_item(slug, _title_from_node(node, a_tag, img_tag, slug), thumb)
            )
        if items:
            used = "%s (%s nodes)" % (selector, len(nodes))
            break
        seen.clear()

    if not items:
        for selector in LINK_SELECTORS:
            try:
                anchors = soup.select(selector)
            except Exception:
                continue
            for a_tag in anchors:
                slug = strip_base(a_tag.get("href") or "")
                if slug in seen or not _usable_slug(slug):
                    continue
                seen.add(slug)
                title = a_tag.get_text(strip=True) or a_tag.get("title") or slug.replace("-", " ").title()
                container = a_tag.find_parent(["article", "li", "div"])
                img_tag = container.find("img") if container else None
                thumb = _extract_img_src(img_tag) if img_tag else ""
                if _is_noise_image(thumb):
                    thumb = ""
                items.append(_build_item(slug, title, thumb))
            if items:
                used = "link fallback %s (%s anchors)" % (selector, len(anchors))
                break

    if not items:
        logger.warning(
            "MoviesDrive parsed 0 cards from %s bytes of HTML - the layout "
            "probably changed, set MD_CARD_SELECTORS or MD_LINK_SELECTORS",
            len(html_text or ""),
        )
    else:
        logger.debug("MoviesDrive parsed %s cards via %s", len(items), used)
    return items


async def _scrape_catalog(url: str, page: int = 1) -> Optional[List[Dict[str, Any]]]:
    page_html = await fetch_html(url)
    if not page_html:
        logger.warning("MoviesDrive catalog page returned no usable HTML: %s", url)
        return None
    items = _parse_cards(page_html)
    if not items:
        logger.warning("MoviesDrive catalog page parsed 0 items: %s", url)
        return None
    if page == 1:
        _note_page_size(len(items))
    return items


def _enrich_item_from_meta(item: dict, meta: dict) -> None:
    if not isinstance(meta, dict):
        return
    # Preserve original item name to prevent showing wrong film name
    if not item.get("name") and meta.get("name"):
        item["name"] = meta["name"]
    if meta.get("imdbRating"):
        item["imdbRating"] = str(meta["imdbRating"])
    if meta.get("description") and not item.get("description"):
        item["description"] = meta["description"]
    if meta.get("releaseInfo") or meta.get("year"):
        item["releaseInfo"] = str(meta.get("releaseInfo") or meta.get("year"))
    if meta.get("genres"):
        genres = meta["genres"]
        item["genres"] = genres if isinstance(genres, list) else [genres]
    if meta.get("background"):
        item["background"] = meta["background"]
    if meta.get("logo"):
        item["logo"] = meta["logo"]


async def _catalog_page_items(
    cat_type: str, cat_id: str, genre: Optional[str], page: int
) -> List[Dict[str, Any]]:
    url = _catalog_url(cat_type, cat_id, genre, page)
    result = await cached_call(
        "cat:" + strip_base(url),
        lambda u=url, p=page: _scrape_catalog(u, page=p),
        ttl=CATALOG_TTL,
        stale_ttl=CATALOG_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )
    return result or []


async def get_catalog_items(
    cat_type: str,
    cat_id: str,
    genre: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
) -> List[Dict[str, Any]]:
    if search:
        search_page = (skip // CATALOG_BATCH_SIZE) + 1
        data = await search_moviesdrive_api(search, page=search_page)
        # The HTML fallback already returns ready-made catalog items.
        html_items = data.get("items") or []
        if html_items:
            return html_items[:CATALOG_BATCH_SIZE]
        items: List[Dict[str, Any]] = []
        for hit in data.get("hits", []):
            doc = hit.get("document", {}) if isinstance(hit, dict) else {}
            slug = (doc.get("permalink") or "").strip("/")
            if not slug:
                continue
            title = doc.get("post_title", "Untitled")
            cleaned_name = clean_title(title) or title
            year_match = re.search(r"\b(19\d\d|20\d\d)\b", title)
            year_str = year_match.group(1) if year_match else ""
            poster_url = absolute(doc.get("post_thumbnail", ""))
            items.append(
                {
                    "id": "moviesdrive:" + slug,
                    "type": "series" if looks_like_series(title) else "movie",
                    "name": cleaned_name,
                    "poster": poster_url,
                    "posterShape": "poster",
                    "background": poster_url,
                    "releaseInfo": year_str,
                    "description": f"📅 Năm: {year_str or 'Mới'}\n🇻🇳 Phụ đề: Tiếng Việt tự động\n⚡ Phát trực tuyến 10Gbps",
                    "genres": ["MoviesDrive", "Tìm kiếm"],
                }
            )
        return items

    per_page = _items_per_page()
    target_start = max(0, skip)
    target_end = target_start + CATALOG_BATCH_SIZE
    start_page = (target_start // per_page) + 1
    end_page = ((target_end - 1) // per_page) + 1
    pages = list(range(start_page, end_page + 1))

    results = await asyncio.gather(
        *[_catalog_page_items(cat_type, cat_id, genre, p) for p in pages]
    )

    all_items: List[Dict[str, Any]] = []
    seen = set()

    def _collect(batch: List[Dict[str, Any]]) -> None:
        for item in batch or []:
            item_id = item.get("id")
            if item_id and item_id not in seen:
                seen.add(item_id)
                all_items.append(item)

    for res in results:
        _collect(res)

    # The page size may have just been learned from page 1, so recompute the
    # offset instead of trusting the hardcoded 24 items per page.
    per_page = _items_per_page()
    offset_in_first_page = max(0, target_start - (start_page - 1) * per_page)
    selected = all_items[offset_in_first_page : offset_in_first_page + CATALOG_BATCH_SIZE]

    if all_items and len(selected) < CATALOG_BATCH_SIZE:
        # Short page: pull one more so skip=20/40 does not return a gap.
        _collect(await _catalog_page_items(cat_type, cat_id, genre, pages[-1] + 1))
        selected = all_items[offset_in_first_page : offset_in_first_page + CATALOG_BATCH_SIZE]

    if all_items and not selected:
        logger.info(
            "MoviesDrive pagination: offset %s is past the %s items parsed for "
            "pages %s (page size %s)",
            offset_in_first_page,
            len(all_items),
            pages,
            per_page,
        )

    # 1. Enrich from cache (both meta and cinemeta caches)
    for item in selected:
        slug = item["id"].replace("moviesdrive:", "").split(":")[0].strip("/")
        mtype = item.get("type", "movie")
        cached_meta = perf.get_cached("meta:" + mtype + ":" + slug) or perf.get_cached("meta:" + slug)
        if cached_meta:
            _enrich_item_from_meta(item, cached_meta)
        else:
            imdb_id = perf.get_cached("md_to_imdb:moviesdrive:" + slug) or perf.get_cached("imdb:" + mtype + ":" + slug)
            if imdb_id:
                cm = perf.get_cached("cinemeta:" + mtype + ":" + imdb_id.split(":")[0])
                if cm:
                    _enrich_item_from_meta(item, cm)

    # 2. Concurrently resolve metadata for uncached items in the first batch.
    #    The old 2.5s budget was shorter than MD_CONNECT_TIMEOUT + one read, so
    #    posters and ratings practically never made it into the first response.
    uncached = [it for it in selected[:META_ENRICH_COUNT] if not it.get("imdbRating")]
    if uncached:
        meta_tasks = [asyncio.create_task(get_meta_object(it.get("type", "movie"), it["id"])) for it in uncached]
        try:
            done, still_running = await asyncio.wait(
                meta_tasks, timeout=META_ENRICH_TIMEOUT
            )
            for t in done:
                res = t.result() if not t.cancelled() and not t.exception() else None
                if res and isinstance(res, dict):
                    res_id = res.get("id")
                    for it in selected:
                        if it.get("id") == res_id:
                            _enrich_item_from_meta(it, res)
                            break
            if still_running:
                # They keep filling the cache for the next request.
                logger.debug(
                    "MoviesDrive meta enrichment: %s of %s finished within %.1fs",
                    len(done),
                    len(meta_tasks),
                    META_ENRICH_TIMEOUT,
                )
        except Exception:
            pass

    # 3. Background pre-warm remaining items on this page
    for item in selected[META_ENRICH_COUNT:CATALOG_BATCH_SIZE]:
        slug = item["id"].replace("moviesdrive:", "").split(":")[0].strip("/")
        mtype = item.get("type", "movie")
        if not perf.get_cached("meta:" + mtype + ":" + slug):
            asyncio.create_task(get_meta_object(mtype, item["id"]))

    return selected


# ------------------------------------------------------------------
# Meta
# ------------------------------------------------------------------
async def _episode_count(content, post_url: str, page_html: str) -> int:
    """Best effort episode count.

    Returns MD_FALLBACK_EPISODES (default 1) when the page gives no hint. The
    old hardcoded 12 invented episodes that could never be resolved.
    """
    archive_links = [
        a["href"]
        for a in content.find_all("a", href=True)
        if "archive/" in a["href"] or "mdrive." in a["href"]
    ]
    if archive_links:
        arc_html = await fetch_html(archive_links[0], referer=post_url, race=False)
        if arc_html:
            arc_soup = make_soup(arc_html)
            hc_links = [
                a["href"]
                for a in arc_soup.find_all("a", href=True)
                if "hubcloud" in a["href"] or "gdflix" in a["href"]
            ]
            if hc_links:
                return len(hc_links)
        logger.info(
            "MoviesDrive could not count episodes from %s, falling back to %s",
            archive_links[0],
            FALLBACK_EPISODES,
        )
        return FALLBACK_EPISODES

    matches = re.findall(r"ep\s*(\d+)|episode\s*(\d+)", page_html, re.I)
    numbers = [int(m[0] or m[1]) for m in matches if (m[0] or m[1])]
    if numbers:
        return min(max(numbers), 60)
    logger.info(
        "MoviesDrive found no episode hint on %s, using %s", post_url, FALLBACK_EPISODES
    )
    return FALLBACK_EPISODES


async def _scrape_meta(media_type: str, item_id: str, slug: str) -> Optional[Dict[str, Any]]:
    post_url = current_base() + "/" + slug + "/"
    page_html = await fetch_html(post_url)
    if not page_html:
        return None

    soup = make_soup(page_html)
    title_tag = soup.find("h1") or soup.find("h2")
    raw_title = title_tag.get_text(strip=True) if title_tag else slug.replace("-", " ").title()
    cleaned_name = clean_title(raw_title) or raw_title

    content = post_content(page_html)
    poster = _extract_meta_poster(soup)

    # 1. Search for IMDb ID in links or resolve via title lookup
    imdb_id = None
    for a in soup.find_all("a", href=True):
        m = re.search(r"(tt\d{7,10})", a["href"])
        if m:
            imdb_id = m.group(1)
            break
    if not imdb_id:
        resolved_id = await find_imdb_for_moviesdrive_id(media_type, item_id)
        if resolved_id:
            imdb_id = resolved_id.split(":")[0]

    # 2. Fetch Cinemeta official metadata if IMDb ID found
    cm_meta = None
    if imdb_id:
        cm_meta = await get_cinemeta_title(media_type, imdb_id)

    # 3. Extract Storyline / Synopsis
    synopsis = ""
    if cm_meta and cm_meta.get("description"):
        synopsis = cm_meta["description"]

    if not synopsis:
        for header in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p", "span", "strong"]):
            htxt = header.get_text(strip=True)
            if any(kw in htxt.lower() for kw in ("storyline", "story:", "plot:", "about movie", "overview", "synopsis")):
                target = header
                for sib in target.next_siblings:
                    if hasattr(sib, "get_text"):
                        st = sib.get_text(" ", strip=True)
                        if st and len(st) > 20 and not any(bad in st.lower() for bad in ("screenshot", "download", "click here")):
                            synopsis = st.strip()
                            break
                if not synopsis and header.parent:
                    for sib in header.parent.next_siblings:
                        if hasattr(sib, "get_text"):
                            st = sib.get_text(" ", strip=True)
                            if st and len(st) > 20 and not any(bad in st.lower() for bad in ("screenshot", "download", "click here")):
                                synopsis = st.strip()
                                break
                if synopsis:
                    break

    # 4. Extract Movie / Series Info box (IMDb rating, Audio/Language, Quality, Year)
    info_dict: Dict[str, str] = {}
    for p in soup.find_all(["p", "div"]):
        txt = p.get_text("\n", strip=True)
        if "Movie Info:" in txt or "Series Info:" in txt or "IMDb Rating" in txt:
            for line in txt.split("\n"):
                line = line.strip()
                if "imdb rating" in line.lower():
                    m = re.search(r"(\d+(?:\.\d+)?\s*/\s*10)", line)
                    if m:
                        info_dict["rating"] = m.group(1).replace(" ", "")
                elif "language" in line.lower() or "audio" in line.lower():
                    val = re.sub(r"^[^\w\s\{\}\[\]\+]+", "", line).strip()
                    val = re.sub(r"^(?:language|audio)\s*:\s*", "", val, flags=re.I).strip()
                    if val:
                        info_dict["audio"] = val
                elif "quality" in line.lower():
                    val = re.sub(r"^quality\s*:\s*", "", line, flags=re.I).strip()
                    if val:
                        info_dict["quality"] = val
                elif "release year" in line.lower() or "year" in line.lower():
                    val = re.search(r"\b(19\d\d|20\d\d)\b", line)
                    if val:
                        info_dict["year"] = val.group(1)

    # 5. Extract metadata fields
    rating = (cm_meta.get("imdbRating") if cm_meta else None) or info_dict.get("rating") or ""
    year = (cm_meta.get("year") if cm_meta else None) or (cm_meta.get("releaseInfo") if cm_meta else None) or info_dict.get("year") or ""
    genres = (cm_meta.get("genres") if cm_meta else None) or ["Action", "HD", "Dual Audio"]
    genre_str = ", ".join(genres) if isinstance(genres, list) else str(genres)
    audio = info_dict.get("audio") or "Dual Audio (Hindi + English / Original)"

    # Prioritize original post poster if present
    if not poster and cm_meta and cm_meta.get("poster"):
        poster = cm_meta.get("poster")
    background = (cm_meta.get("background") if cm_meta else None) or poster or ""
    logo = (cm_meta.get("logo") if cm_meta else None) or ""
    # Always keep original cleaned movie title so we never replace it with a wrong movie
    final_name = cleaned_name or raw_title

    # 6. Translate Synopsis & Build Vietnamese Rich Description
    vi_synopsis = ""
    if synopsis:
        try:
            from translation_service import translate_to_vietnamese
            vi_synopsis = await translate_to_vietnamese(synopsis)
        except Exception:
            vi_synopsis = synopsis

    header_parts = []
    if rating:
        header_parts.append(f"⭐ IMDb: {rating}")
    if year:
        header_parts.append(f"📅 Năm: {year}")
    if genre_str:
        header_parts.append(f"🎭 Thể loại: {genre_str}")

    desc_lines = []
    if header_parts:
        desc_lines.append(" | ".join(header_parts))
    desc_lines.append(f"🔊 Âm thanh: {audio}")
    desc_lines.append("🇻🇳 Phụ đề: Tiếng Việt tự động (AI Fast & Quality)")
    desc_lines.append("⚡ Máy chủ phát: Direct CDN 10Gbps / Local Proxy Stream")
    desc_lines.append("")
    if vi_synopsis:
        desc_lines.append("📝 Tóm tắt nội dung:")
        desc_lines.append(vi_synopsis)
    else:
        desc_lines.append(f"🎬 Xem phim {final_name} trên MoviesDrive với chất lượng 4K UHD, 1080p FHD, 720p HD, hỗ trợ phụ đề tiếng Việt và phát trực tuyến tốc độ cao.")

    formatted_description = "\n".join(desc_lines)

    is_series = bool(media_type == "series" or re.search(r"season|s\d+|series", raw_title, re.I))
    videos: List[Dict[str, Any]] = []

    if is_series:
        season_match = re.search(r"season\s*(\d+)|s(\d+)", raw_title, re.I)
        season_num = (
            int(season_match.group(1) or season_match.group(2)) if season_match else 1
        )
        ep_count = await _episode_count(content, post_url, page_html)
        for ep in range(1, max(0, ep_count) + 1):
            videos.append(
                {
                    "id": "moviesdrive:" + slug + ":" + str(season_num) + ":" + str(ep),
                    "title": "Tập " + str(ep) + " (Episode " + str(ep) + ")",
                    "season": season_num,
                    "episode": ep,
                    "released": "2026-01-01T00:00:00.000Z",
                }
            )

    meta_obj: Dict[str, Any] = {
        "id": item_id,
        "type": "series" if is_series else "movie",
        "name": final_name,
        "poster": poster,
        "background": background,
        "logo": logo,
        "description": formatted_description,
        "genres": genres if isinstance(genres, list) else [genres],
        "releaseInfo": str(year) if year else "",
        "imdbRating": str(rating) if rating else "",
        "imdb_id": imdb_id or "",
        "posterShape": "poster",
    }
    if videos:
        meta_obj["videos"] = videos
    return meta_obj


async def get_meta_object(media_type: str, item_id: str) -> Dict[str, Any]:
    if not item_id.startswith("moviesdrive:"):
        return {}
    slug = item_id.replace("moviesdrive:", "").split(":")[0].strip("/")
    if not slug:
        return {}
    meta = await cached_call(
        "meta:" + media_type + ":" + slug,
        lambda: _scrape_meta(media_type, item_id, slug),
        ttl=META_TTL,
        stale_ttl=META_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )
    return meta or {}


# ------------------------------------------------------------------
# Cinemeta / OpenSubtitles / id mapping
# ------------------------------------------------------------------
async def get_cinemeta_title(item_type: str, imdb_id: str) -> Optional[Dict[str, Any]]:
    url = CINEMETA_API + "/" + item_type + "/" + urllib.parse.quote(imdb_id) + ".json"

    async def factory():
        data = await perf.fetch_json(url)
        if isinstance(data, dict):
            return data.get("meta") or None
        return None

    return await cached_call(
        "cinemeta:" + item_type + ":" + imdb_id,
        factory,
        ttl=CINEMETA_TTL,
        stale_ttl=IMDB_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


async def fetch_opensubtitles(imdb_id: str, media_type: str = "movie", extra: str = "") -> list:
    if not imdb_id or not imdb_id.startswith("tt"):
        return []
    url = OPENSUBTITLES_BASE + media_type + "/" + urllib.parse.quote(imdb_id)
    if extra:
        url = url + "/" + urllib.parse.quote(extra)
    url = url + ".json"

    async def factory():
        data = await perf.fetch_json(url)
        if isinstance(data, dict):
            return data.get("subtitles") or None
        return None

    subs = await cached_call(
        "osubs:" + media_type + ":" + imdb_id + ":" + (extra or ""),
        factory,
        ttl=SUBS_TTL,
        stale_ttl=IMDB_TTL,
        negative_ttl=NEGATIVE_TTL,
    )
    return subs or []


async def _lookup_imdb(media_type: str, clean_title: str, season: int, episode: int, year: Optional[str] = None):
    url = (
        CINEMETA_CATALOG
        + "/"
        + media_type
        + "/top/search="
        + urllib.parse.quote(clean_title)
        + ".json"
    )
    data = await perf.fetch_json(url)
    if not isinstance(data, dict):
        return None
    metas = data.get("metas") or []
    if not metas:
        return None

    # Strict title & year validation: DO NOT pick a random result if title does not match
    def _norm(s: str) -> str:
        s = re.sub(r"[^\w\s]", "", (s or "").lower())
        return re.sub(r"\s+", " ", s).strip()

    def _safe_year(val: Any) -> Optional[int]:
        if not val:
            return None
        m = re.search(r"\b(19\d\d|20\d\d)\b", str(val))
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        return None

    target_norm = _norm(clean_title)
    if not target_norm:
        return None

    target_words = [w for w in target_norm.split() if w not in ('a', 'an', 'the', 'and', 'or', 'of', 'in', 'to', 'for', 'with') and len(w) > 1]
    if not target_words:
        target_words = target_norm.split()

    target_year = _safe_year(year)

    matched_meta = None
    for m in metas:
        m_name = _norm(m.get("name", ""))
        if not m_name:
            continue
        m_year = _safe_year(m.get("year") or m.get("releaseInfo"))
        # Exact match or starts with
        if m_name == target_norm or m_name.startswith(target_norm) or target_norm.startswith(m_name):
            if target_year and m_year and abs(target_year - m_year) > 1:
                continue
            matched_meta = m
            break
        # All major words must be in m_name and word count difference must not be large
        if all(w in m_name for w in target_words):
            m_words = m_name.split()
            if abs(len(m_words) - len(target_norm.split())) <= 2:
                if target_year and m_year and abs(target_year - m_year) > 1:
                    continue
                matched_meta = m
                break

    if not matched_meta:
        return None

    imdb_id = matched_meta.get("imdb_id") or matched_meta.get("id")
    if not imdb_id or not imdb_id.startswith("tt"):
        return None
    if media_type == "series":
        return imdb_id + ":" + str(season) + ":" + str(episode)
    return imdb_id


async def find_imdb_for_moviesdrive_id(media_type: str, md_id: str) -> Optional[str]:
    """Resolve a MoviesDrive slug id to an IMDb id via Cinemeta search."""
    parts = md_id.split(":")
    if len(parts) < 2:
        return None
    slug = parts[1]
    season = int(parts[2]) if len(parts) > 2 else 1
    episode = int(parts[3]) if len(parts) > 3 else 1

    clean = slug
    for word in NOISE_WORDS:
        clean = re.sub(r"\b" + word + r"\b", "", clean, flags=re.I)

    year_match = re.search(r"\b(19\d\d|20\d\d)\b", clean)
    year = year_match.group(1) if year_match else None

    clean_title = re.sub(r"\b(19\d\d|20\d\d)\b", "", clean)
    clean_title = re.sub(r"season-\d+", "", clean_title, flags=re.I)
    clean_title = clean_title.replace("-", " ").strip()
    if not clean_title:
        return None

    return await cached_call(
        "md_to_imdb:" + md_id,
        lambda: _lookup_imdb(media_type, clean_title, season, episode, year=year),
        ttl=IMDB_TTL,
        negative_ttl=perf._env_int("MD_IMDB_NEGATIVE_TTL", 600),
    )


# ------------------------------------------------------------------
# Prewarming
# ------------------------------------------------------------------
def prewarm_jobs() -> List[Callable[[], Any]]:
    """The catalogs Stremio asks for the moment the addon is opened."""
    return [
        lambda: get_catalog_items("movie", "moviesdrive_movies_latest"),
        lambda: get_catalog_items("movie", "moviesdrive_movies_4k"),
        lambda: get_catalog_items("series", "moviesdrive_series_latest"),
    ]

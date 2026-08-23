"""
Catalog, metadata, and Cinemeta mapping layer for 4KHDHub addon.
"""

import asyncio
import html as html_lib
import json
import logging
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

import fourkhdhub_perf as perf
from fourkhdhub_perf import (
    NEGATIVE_TTL,
    base_of,
    cached_call,
    fetch_json,
    make_soup,
    mirror_candidates,
    note_active_base,
    race_fetch_text,
)
import fourkhdhub_resolver as resolver
from fourkhdhub_resolver import (
    absolute,
    current_base,
    strip_base,
)

logger = logging.getLogger("fourkhdhub_addon")

CINEMETA_BASE = "https://v3-cinemeta.strem.io"
CINEMETA_API = CINEMETA_BASE + "/meta"
CINEMETA_CATALOG = CINEMETA_BASE + "/catalog"

CATALOG_TTL = perf._env_int("FOURKHD_CATALOG_TTL", 300)
CATALOG_STALE_TTL = perf._env_int("FOURKHD_CATALOG_STALE_TTL", 1800)
CATALOG_TTL = 3600
CATALOG_STALE_TTL = 86400
SEARCH_TTL = perf._env_int("FOURKHD_SEARCH_TTL", 600)
META_TTL = perf._env_int("FOURKHD_META_TTL", 900)
META_STALE_TTL = perf._env_int("FOURKHD_META_STALE_TTL", 7200)
CINEMETA_TTL = perf._env_int("FOURKHD_CINEMETA_TTL", 3600)
IMDB_TTL = perf._env_int("FOURKHD_IMDB_TTL", 86400)
WP_ITEMS_PER_PAGE = 18
STREMIO_PAGE_SIZE = perf._env_int("FOURKHD_CATALOG_PAGE_SIZE", 54)
PAGE_SIZE = STREMIO_PAGE_SIZE
SEARCH_PAGE_SIZE = 18

CATEGORIES_MAP = {
    "Tất cả": "movies",
    "Phim Mới": "movies",
    "4K HDR": "2160p-HDR",
    "English Movies": "english-movies",
    "Hindi Movies": "hindi-movies",
    "Web Series": "series",
    "English Series": "english-series",
    "Hindi Series": "hindi-series",
    "Korean Series": "korean-series",
    "Drama Series": "drama-series",
    "Netflix": "netflix",
    "Amazon Prime Video": "amazon_prime_video",
    "Disney+": "disney",
    "HBO Max": "hbo_max",
    "Anime": "anime",
    "Top IMDb": "imdb",
}
GENRE_OPTIONS = list(CATEGORIES_MAP.keys())

SKIP_SLUG_WORDS = ("category", "tag", "contact", "dmca", "privacy", "how-to-download", "disclaimer", "about")
SERIES_PATTERN = re.compile(r"season|s\d+|series|episodes?|ep\d+", re.I)


def looks_like_series(title: str, url: str) -> bool:
    return bool("-series-" in url or SERIES_PATTERN.search(title) or SERIES_PATTERN.search(url))


def clean_title(title: str) -> str:
    t = title or ""
    t = html_lib.unescape(t).replace("’", "'").replace("‘", "'").replace("`", "'")
    t = re.sub(r"^Download\s+", "", t, flags=re.I).strip()
    t = re.sub(r"^[^\w\s]+", "", t).strip()
    t = re.sub(r"\((20\d\d|19\d\d)\)", r"\1", t)
    t = re.sub(r"\[(?:Extended Cut|Added|Unrated|IMAX|REMASTERED|Director'?s Cut)[^\]]*\]", "", t, flags=re.I)
    t = re.sub(r"\{(?:Added|Hindi-English|English|Dual Audio|Multi Audio)[^\}]*\}", "", t, flags=re.I)
    t = re.sub(
        r"[\(\[\{]\s*(?:WEB-DL|WEBRip|BluRay|HDTC|DS4K|4K|1080p|720p|480p|HEVC|10Bit|x264|x265|Dual Audio|Hindi|English|Tamil|Telugu|Punjabi|ESubs?|Multi Audio|Full Movie|ALL Episodes|NF Series|PrimeVideo Series|HBO Series|EP[\s\-]*\d+\s*Added|Without-ADs|HQ[/\-]Studio Dub)[^\)\]\}]*[\)\]\}]",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"\b(?:WEB-DL|WEBRip|BluRay|HDTC|DS4K|4K|1080p|720p|480p|HEVC|10Bit|x264|x265|Dual Audio|Hindi|English|Tamil|Telugu|Punjabi|ESubs?|Multi Audio|Full Movie|ALL Episodes)\b.*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"[\–\-\|]\s*(?:4KHDHub|HDHub4U|Full Movie|Official|ALL Episodes|Season \d+).*", "", t, flags=re.I)
    t = re.sub(r"[\[\]\(\)\|\-–—]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------
# Scraping Items from HTML (Search & Catalog)
# ------------------------------------------------------------------
def _parse_movie_cards(html: str) -> List[Dict[str, Any]]:
    if not html:
        return []

    soup = make_soup(html)
    items: List[Dict[str, Any]] = []
    seen_slugs = set()

    for a in soup.select("a.movie-card, .movie-card a, a[href*='-movie-'], a[href*='-series-']"):
        href = a.get("href", "")
        if not href or href.startswith("#"):
            continue

        slug = href.strip("/").split("/")[-1]
        if not slug or any(skip in slug.lower() for skip in SKIP_SLUG_WORDS):
            continue
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Extract title from card image or card content
        img = a.find("img")
        img_alt = img.get("alt", "") if img else ""
        poster = img.get("src") or img.get("data-src") if img else ""

        # Content container
        content_div = a.select_one(".movie-card-content, .card-content")
        raw_title = ""
        if content_div:
            title_tag = content_div.find(["h2", "h3", "h4", "div", "span"])
            raw_title = title_tag.get_text(strip=True) if title_tag else content_div.get_text(" ", strip=True)
        if not raw_title:
            raw_title = img_alt or slug.replace("-", " ").title()

        cleaned_title = clean_title(raw_title)

        # Extract Year
        year_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title) or re.search(r"\b(19\d\d|20\d\d)\b", slug)
        year = int(year_m.group(1)) if year_m else None

        # Extract badges
        formats = [b.get_text(strip=True) for b in a.select(".movie-card-format, .quality-badge, .badge")]
        desc_parts = []
        if formats:
            desc_parts.append(" • ".join(formats[:4]))
        desc_parts.append(f"4KHDHub 4K Ultra HD & Dolby Vision")
        desc = " | ".join(desc_parts)

        is_series = looks_like_series(raw_title, href)
        item_type = "series" if is_series else "movie"

        full_url = absolute(href)

        items.append({
            "id": f"4khdhub:{slug}",
            "type": item_type,
            "name": cleaned_title or raw_title,
            "poster": poster,
            "posterShape": "poster",
            "year": year,
            "releaseInfo": str(year) if year else None,
            "description": desc,
            "genres": [f for f in formats if f not in ("4K", "HDR", "DV", "BD", "FHD", "1080p", "2160p", "Movies", "Series")][:3],
            "slug": slug,
            "url": full_url,
        })

    return items


async def _lookup_imdb_id(title: str, year: Optional[int], media_type: str) -> Optional[str]:
    clean_t = clean_title(title)
    if not clean_t:
        return None
    key = f"fourkhd_imdb:{media_type}:{clean_t}:{year or ''}"

    async def _fetch():
        search_query = f"{clean_t} {year}" if year else clean_t
        url = f"{CINEMETA_CATALOG}/{media_type}/top/search={urllib.parse.quote(search_query)}.json"
        data = await perf.fetch_json(url)
        metas = []
        if isinstance(data, dict):
            metas = data.get("metas") or []
        if not metas and year:
            url2 = f"{CINEMETA_CATALOG}/{media_type}/top/search={urllib.parse.quote(clean_t)}.json"
            data2 = await perf.fetch_json(url2)
            if isinstance(data2, dict):
                metas = data2.get("metas") or []
        if not metas:
            return None

        target_norm = re.sub(r"[^\w\s]", "", clean_t.lower()).strip()
        for m in metas:
            m_name = re.sub(r"[^\w\s]", "", (m.get("name") or "").lower()).strip()
            if m_name == target_norm:
                m_year = None
                try:
                    m_year = int(str(m.get("year") or "")[:4])
                except Exception:
                    pass
                if not year or not m_year or abs(year - m_year) <= 1:
                    return m.get("id")
        return metas[0].get("id") if metas else None

    return await cached_call(
        key, _fetch, ttl=IMDB_TTL, stale_ttl=IMDB_TTL * 2, negative_ttl=NEGATIVE_TTL
    )


async def enrich_catalog_with_imdb(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
    tasks = [
        _lookup_imdb_id(it.get("name") or "", it.get("year"), it.get("type") or "movie")
        for it in items
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    enriched = []
    for it, res in zip(items, results):
        item_copy = dict(it)
        if isinstance(res, str) and res.startswith("tt"):
            item_copy["id"] = res
        enriched.append(item_copy)
    return enriched


# ------------------------------------------------------------------
# Catalog Fetching & Pagination
# ------------------------------------------------------------------
async def get_catalog_page(category_slug: str, page: int = 1) -> List[Dict[str, Any]]:
    key = f"fourkhd_cat:{category_slug}:{page}"

    async def _fetch():
        base = current_base()
        clean_cat = category_slug.strip("/")
        if clean_cat == "movies" or not clean_cat:
            url = f"{base}/category/movies/page/{page}/" if page > 1 else f"{base}/category/movies/"
        else:
            url = f"{base}/category/{clean_cat}/page/{page}/" if page > 1 else f"{base}/category/{clean_cat}/"

        candidates = mirror_candidates(url)
        html, _ = await race_fetch_text(candidates)
        return _parse_movie_cards(html)

    return await cached_call(
        key, _fetch, ttl=CATALOG_TTL, stale_ttl=CATALOG_STALE_TTL, negative_ttl=NEGATIVE_TTL
    ) or []


async def get_catalog_items(category: str = "Tất cả", skip: int = 0) -> List[Dict[str, Any]]:
    category_slug = CATEGORIES_MAP.get(category, "movies")
    target_start = max(0, skip)
    target_end = target_start + STREMIO_PAGE_SIZE
    start_wp_page = (target_start // WP_ITEMS_PER_PAGE) + 1
    end_wp_page = ((target_end - 1) // WP_ITEMS_PER_PAGE) + 1
    wp_pages = list(range(start_wp_page, end_wp_page + 1))

    results = await asyncio.gather(
        *[get_catalog_page(category_slug, page=p) for p in wp_pages]
    )

    all_items: List[Dict[str, Any]] = []
    seen = set()
    for batch in results:
        for it in batch or []:
            it_key = it.get("slug") or it.get("url") or it.get("id")
            if it_key and it_key not in seen:
                seen.add(it_key)
                all_items.append(it)

    offset_in_first_page = max(0, target_start - (start_wp_page - 1) * WP_ITEMS_PER_PAGE)
    selected = all_items[offset_in_first_page : offset_in_first_page + STREMIO_PAGE_SIZE]
    # Enrich with IMDb IDs so third-party subtitle addons (OpenSubtitles, etc.) work automatically!
    return await enrich_catalog_with_imdb(selected)


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------
async def search_fourkhdhub(query: str, page: int = 1) -> List[Dict[str, Any]]:
    clean_q = urllib.parse.quote(query.strip())
    key = f"fourkhd_search:{clean_q}:{page}"

    async def _fetch():
        base = current_base()
        url = f"{base}/page/{page}/?s={clean_q}" if page > 1 else f"{base}/?s={clean_q}"
        candidates = mirror_candidates(url)
        html, _ = await race_fetch_text(candidates)
        cards = _parse_movie_cards(html)
        return await enrich_catalog_with_imdb(cards)

    return await cached_call(
        key, _fetch, ttl=SEARCH_TTL, stale_ttl=CATALOG_STALE_TTL, negative_ttl=NEGATIVE_TTL
    ) or []


# ------------------------------------------------------------------
# Cinemeta Mapping & IMDb Bridge
# ------------------------------------------------------------------
async def get_cinemeta_meta(type_: str, imdb_id: str) -> Optional[Dict[str, Any]]:
    key = f"fourkhd:cinemeta:{type_}:{imdb_id}"

    async def _fetch():
        url = f"{CINEMETA_API}/{type_}/{imdb_id}.json"
        data = await fetch_json(url, timeout=6.0)
        return data.get("meta") if isinstance(data, dict) else None

    return await cached_call(key, _fetch, ttl=CINEMETA_TTL, negative_ttl=NEGATIVE_TTL)


async def find_fourkhdhub_for_imdb(
    imdb_id: str,
    title: Optional[str] = None,
    year: Optional[int] = None,
    media_type: str = "movie",
) -> List[Dict[str, Any]]:
    """Match IMDb ID to the best corresponding 4KHDHub post items (ranked)."""
    if not imdb_id:
        return []

    is_series = (media_type == "series")
    key = f"fourkhd:imdb_map:{imdb_id}"
    cached_val, hit = perf.get_cached(key)
    if hit and cached_val is not None:
        return cached_val

    # If title/year not provided, resolve via Cinemeta
    if not title:
        meta = await get_cinemeta_meta("series" if is_series else "movie", imdb_id)
        if meta:
            title = meta.get("name")
            year_val = meta.get("year")
            if year_val:
                try:
                    year = int(str(year_val)[:4])
                except Exception:
                    pass

    if not title:
        perf.set_cached(key, [], ttl=NEGATIVE_TTL)
        return []

    # Search 4KHDHub for title
    search_results = await search_fourkhdhub(title, page=1)
    if not search_results:
        # Try simplified query without punctuation
        simplified = re.sub(r"[^\w\s]", " ", title).strip()
        if simplified != title:
            search_results = await search_fourkhdhub(simplified, page=1)

    if not search_results:
        perf.set_cached(key, [], ttl=NEGATIVE_TTL)
        return []

    # Score and rank all matches
    scored_items: List[Tuple[int, Dict[str, Any]]] = []
    target_clean = clean_title(title).lower()

    for item in search_results:
        item_name = item.get("name", "").lower()
        score = 0
        if target_clean == item_name:
            score += 100
        elif target_clean in item_name or item_name in target_clean:
            score += 60

        # Exact word overlap
        target_words = set(re.findall(r"\w+", target_clean))
        item_words = set(re.findall(r"\w+", item_name))
        common = target_words.intersection(item_words)
        score += len(common) * 15

        # Year match
        item_year = item.get("year")
        if year and item_year:
            if abs(year - item_year) <= 1:
                score += 30
            else:
                score -= 20

        # Series / Movie type alignment
        if is_series and item.get("type") == "series":
            score += 35
        elif not is_series and item.get("type") == "movie":
            score += 35

        if score >= 35:
            scored_items.append((score, item))

    scored_items.sort(key=lambda x: x[0], reverse=True)
    results = [it[1] for it in scored_items]

    if results:
        perf.set_cached(key, results, ttl=IMDB_TTL)
        return results

    perf.set_cached(key, [], ttl=NEGATIVE_TTL)
    return []


# ------------------------------------------------------------------
# Meta Construction
# ------------------------------------------------------------------
async def get_meta_for_slug(slug: str, item_type: str = "movie") -> Optional[Dict[str, Any]]:
    clean_slug = slug.strip("/")
    post_url = absolute(clean_slug)
    key = f"fourkhd:meta:{clean_slug}"

    async def _fetch():
        html = await resolver.get_post_page(post_url)
        if not html:
            return None

        soup = make_soup(html)
        title_tag = soup.select_one("h1.page-title, h1, .entry-title")
        raw_title = title_tag.get_text(strip=True) if title_tag else clean_slug.replace("-", " ").title()
        cleaned_title = clean_title(raw_title)

        year_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
        year = int(year_m.group(1)) if year_m else None

        img_tag = soup.select_one(".movie-card-image img, article img, main img, img[src*='image.tmdb.org']")
        poster = img_tag.get("src") or img_tag.get("data-src") if img_tag else ""

        # Description
        desc_p = soup.select_one(".movie-description, .entry-content p, article p")
        description = desc_p.get_text(strip=True) if desc_p else f"Watch {cleaned_title} in 4K UHD, HDR10+, Dolby Vision on 4KHDHub."

        # Genres
        genres = []
        for badge in soup.select(".quality-badge, .movie-card-format, .badge"):
            t = badge.get_text(strip=True)
            if t and t not in genres and not any(w in t.lower() for w in ("4k", "hdr", "1080p", "2160p", "bd", "fhd", "hevc")):
                genres.append(t)

        is_series = looks_like_series(raw_title, clean_slug)
        actual_type = "series" if is_series else "movie"

        meta: Dict[str, Any] = {
            "id": f"4khdhub:{clean_slug}",
            "type": actual_type,
            "name": cleaned_title,
            "poster": poster,
            "posterShape": "poster",
            "background": poster,
            "description": description,
            "year": year,
            "releaseInfo": str(year) if year else None,
            "genres": genres[:4],
        }

        # Build videos list for series
        if actual_type == "series":
            buttons = await resolver.resolve_all_download_buttons_from_post(post_url)
            seasons_eps: Dict[int, set] = {}
            for b in buttons:
                s = b.get("season") or 1
                e = b.get("episode") or 1
                seasons_eps.setdefault(s, set()).add(e)

            videos: List[Dict[str, Any]] = []
            for s in sorted(seasons_eps.keys()):
                for e in sorted(seasons_eps[s]):
                    videos.append({
                        "id": f"4khdhub:{clean_slug}:{s}:{e}",
                        "title": f"Mùa {s} Tập {e}",
                        "season": s,
                        "episode": e,
                        "released": f"{year}-01-01T00:00:00.000Z" if year else None,
                    })
            if not videos:
                # Default S01E01 fallback
                videos.append({
                    "id": f"4khdhub:{clean_slug}:1:1",
                    "title": f"Mùa 1 Tập 1",
                    "season": 1,
                    "episode": 1,
                })
            meta["videos"] = videos

        return meta

    return await cached_call(
        key, _fetch, ttl=META_TTL, stale_ttl=META_STALE_TTL, negative_ttl=NEGATIVE_TTL
    )


# ------------------------------------------------------------------
# Reverse Lookup: 4KHDHub slug -> IMDb ID
# ------------------------------------------------------------------
OPENSUBTITLES_BASE = "https://opensubtitles-v3.strem.io/subtitles/"
SUBS_TTL = perf._env_int("FOURKHD_SUBS_TTL", 900)


async def find_imdb_for_fourkhdhub_slug(slug: str, media_type: str = "movie") -> Optional[str]:
    meta = await get_meta_for_slug(slug, item_type=media_type)
    if not meta or not meta.get("name"):
        return None

    title = meta["name"]
    year = meta.get("year")

    # Search Cinemeta for title
    url = f"{CINEMETA_CATALOG}/{media_type}/top/search={urllib.parse.quote(title)}.json"
    data = await perf.fetch_json(url)
    if not isinstance(data, dict):
        return None
    metas = data.get("metas") or []
    if not metas:
        return None

    target_norm = re.sub(r"[^\w\s]", "", title.lower()).strip()
    for m in metas:
        m_name = re.sub(r"[^\w\s]", "", (m.get("name") or "").lower()).strip()
        if m_name == target_norm:
            m_year = None
            try:
                m_year = int(str(m.get("year") or "")[:4])
            except Exception:
                pass
            if not year or not m_year or abs(year - m_year) <= 1:
                return m.get("id")

    return metas[0].get("id") if metas else None


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


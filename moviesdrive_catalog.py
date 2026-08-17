"""
Catalog, meta and id-mapping layer for the MoviesDrive addon.

Everything here is served through moviesdrive_perf.cached_call, which gives:

* single flight - ten viewers opening the same page cause one scrape
* stale-while-revalidate - an expired catalog is returned instantly and
  refreshed in the background, so nobody ever waits for a scrape
* negative caching - a miss is remembered for a minute instead of rescraping
* disk persistence - a restart keeps the imdb and cinemeta mappings
"""

import asyncio
import json
import logging
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

import moviesdrive_perf as perf
from moviesdrive_perf import (
    NEGATIVE_TTL,
    base_of,
    cached_call,
    make_soup,
    note_active_base,
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
MD_ITEMS_PER_PAGE = 24
CATALOG_BATCH_SIZE = perf._env_int("MD_CATALOG_PAGE_SIZE", 72)

CATEGORIES_MAP = {
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
    "Sci-Fi": "sifi",
    "South": "south",
    "Thriller": "triller",
    "War": "war",
    "2160p 4K": "2160p-4k",
}
GENRE_OPTIONS = list(CATEGORIES_MAP.keys())

SKIP_SLUG_WORDS = ("category", "tag", "contact", "dmca", "privacy")
NOISE_WORDS = (
    "web-dl", "hindi", "dd5-1", "english", "480p", "720p", "1080p",
    "2160p", "4k", "sdr", "x264", "esubs", "full-movie", "esub",
)


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------
async def _search_request(query: str, page: int) -> Optional[Dict[str, Any]]:
    path = "/search.php?q=" + urllib.parse.quote(query) + "&page=" + str(page)
    urls = [current_base() + path]
    for base in ALL_BASES:
        candidate = base.rstrip("/") + path
        if candidate not in urls:
            urls.append(candidate)

    headers = {
        "User-Agent": perf.USER_AGENT,
        "Referer": current_base() + "/search.html",
        "Accept": "application/json",
    }
    text, final_url = await race_fetch_text(urls, headers=headers)
    if not text:
        return None
    winner = base_of(final_url, ALL_BASES)
    if winner:
        note_active_base(winner)
    try:
        data = json.loads(text)
    except Exception as exc:
        logger.warning("MoviesDrive search returned invalid JSON for %s: %s", query, exc)
        return None
    if isinstance(data, dict) and data.get("hits"):
        return data
    return None


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
def _catalog_url(cat_type: str, cat_id: str, genre: Optional[str], page: int) -> str:
    base = current_base()
    if cat_id == "moviesdrive_movies_4k":
        url = base + "/category/2160p-4k/"
    elif genre and genre in CATEGORIES_MAP:
        url = base + "/category/" + CATEGORIES_MAP[genre] + "/"
    elif cat_type == "series" or cat_id == "moviesdrive_series_latest":
        url = base + "/category/web/"
    else:
        url = base + "/category/movies/"
    if page > 1:
        url = url + "page/" + str(page) + "/"
    return url


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


def _parse_cards(html_text: str) -> List[Dict[str, Any]]:
    soup = make_soup(html_text)
    nodes = soup.find_all("div", class_="poster-card") or soup.find_all("article")
    items: List[Dict[str, Any]] = []
    seen = set()

    for node in nodes:
        a_tag = node.find_parent("a", href=True) or node.find("a", href=True)
        if not a_tag:
            continue
        slug = strip_base(a_tag["href"])
        if not slug or slug in seen:
            continue
        if any(word in slug.lower() for word in SKIP_SLUG_WORDS):
            continue
        seen.add(slug)

        img_tag = node.find("img")
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

        cleaned_name = clean_title(title) or title

        thumb = ""
        if img_tag:
            thumb = _extract_img_src(img_tag)
            if _is_noise_image(thumb):
                thumb = ""

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

        audio_match = re.search(r"\[([^\]]*(?:Hindi|English|Tamil|Telugu|Kannada|Malayalam|Dual|Multi)[^\]]*)\]", title, re.I)
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
        items.append(
            {
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
        )
    return items


async def _scrape_catalog(url: str) -> Optional[List[Dict[str, Any]]]:
    page_html = await fetch_html(url)
    if not page_html:
        return None
    return _parse_cards(page_html) or None


def _enrich_item_from_meta(item: dict, meta: dict) -> None:
    if not isinstance(meta, dict):
        return
    if meta.get("name"):
        item["name"] = meta["name"]
    if meta.get("imdbRating"):
        item["imdbRating"] = str(meta["imdbRating"])
    if meta.get("description"):
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


async def get_catalog_items(
    cat_type: str,
    cat_id: str,
    genre: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
) -> List[Dict[str, Any]]:
    if search:
        search_page = (skip // 20) + 1
        data = await search_moviesdrive_api(search, page=search_page)
        items: List[Dict[str, Any]] = []
        for hit in data.get("hits", []):
            doc = hit.get("document", {})
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

    target_start = max(0, skip)
    target_end = target_start + CATALOG_BATCH_SIZE
    start_page = (target_start // MD_ITEMS_PER_PAGE) + 1
    end_page = ((target_end - 1) // MD_ITEMS_PER_PAGE) + 1
    offset_in_first_page = target_start % MD_ITEMS_PER_PAGE

    page_urls = [
        _catalog_url(cat_type, cat_id, genre, p)
        for p in range(start_page, end_page + 1)
    ]
    tasks = [
        cached_call(
            "cat:" + strip_base(u),
            lambda u=u: _scrape_catalog(u),
            ttl=CATALOG_TTL,
            stale_ttl=CATALOG_STALE_TTL,
            negative_ttl=NEGATIVE_TTL,
        )
        for u in page_urls
    ]
    results = await asyncio.gather(*tasks)
    all_items: List[Dict[str, Any]] = []
    seen = set()
    for res in results:
        if res:
            for item in res:
                item_id = item.get("id")
                if item_id and item_id not in seen:
                    seen.add(item_id)
                    all_items.append(item)

    selected = all_items[offset_in_first_page : offset_in_first_page + CATALOG_BATCH_SIZE]

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

    # 2. Concurrently resolve metadata for uncached items in the first batch (up to 8 items) with timeout
    uncached = [it for it in selected[:8] if not it.get("imdbRating")]
    if uncached:
        meta_tasks = [asyncio.create_task(get_meta_object(it.get("type", "movie"), it["id"])) for it in uncached]
        try:
            done, _ = await asyncio.wait(meta_tasks, timeout=2.5)
            for t in done:
                res = t.result() if not t.cancelled() and not t.exception() else None
                if res and isinstance(res, dict):
                    res_id = res.get("id")
                    for it in selected:
                        if it.get("id") == res_id:
                            _enrich_item_from_meta(it, res)
                            break
        except Exception:
            pass

    # 3. Background pre-warm remaining items on this page
    for item in selected[8:24]:
        slug = item["id"].replace("moviesdrive:", "").split(":")[0].strip("/")
        mtype = item.get("type", "movie")
        if not perf.get_cached("meta:" + mtype + ":" + slug):
            asyncio.create_task(get_meta_object(mtype, item["id"]))

    return selected


# ------------------------------------------------------------------
# Meta
# ------------------------------------------------------------------
async def _episode_count(content, post_url: str, page_html: str) -> int:
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
        return 12

    matches = re.findall(r"ep\s*(\d+)|episode\s*(\d+)", page_html, re.I)
    numbers = [int(m[0] or m[1]) for m in matches if (m[0] or m[1])]
    if numbers:
        return min(max(numbers), 60)
    return 12


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

    if not poster and cm_meta and cm_meta.get("poster"):
        poster = cm_meta.get("poster")
    background = (cm_meta.get("background") if cm_meta else None) or poster or ""
    logo = (cm_meta.get("logo") if cm_meta else None) or ""
    final_name = (cm_meta.get("name") if cm_meta else None) or cleaned_name or raw_title

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
        for ep in range(1, ep_count + 1):
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


async def _lookup_imdb(media_type: str, clean_title: str, season: int, episode: int):
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
    imdb_id = metas[0].get("imdb_id") or metas[0].get("id")
    if not imdb_id:
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
    clean_title = re.sub(r"\b(19\d\d|20\d\d)\b", "", clean)
    clean_title = re.sub(r"season-\d+", "", clean_title, flags=re.I)
    clean_title = clean_title.replace("-", " ").strip()
    if not clean_title:
        return None

    return await cached_call(
        "md_to_imdb:" + md_id,
        lambda: _lookup_imdb(media_type, clean_title, season, episode),
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

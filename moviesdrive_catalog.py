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
PAGE_SIZE = perf._env_int("MD_CATALOG_PAGE_SIZE", 18)

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
    url = base + "/"
    if cat_id == "moviesdrive_movies_4k":
        url = base + "/category/2160p-4k/"
    elif genre and genre in CATEGORIES_MAP:
        url = base + "/category/" + CATEGORIES_MAP[genre] + "/"
    elif cat_type == "series":
        url = base + "/category/web/"
    if page > 1:
        url = url + "page/" + str(page) + "/"
    return url


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

        thumb = ""
        if img_tag:
            thumb = img_tag.get("src") or img_tag.get("data-src") or ""

        items.append(
            {
                "id": "moviesdrive:" + slug,
                "type": "series" if looks_like_series(title) else "movie",
                "name": title,
                "poster": absolute(thumb),
                "posterShape": "poster",
            }
        )
    return items


async def _scrape_catalog(url: str) -> Optional[List[Dict[str, Any]]]:
    page_html = await fetch_html(url)
    if not page_html:
        return None
    return _parse_cards(page_html) or None


async def get_catalog_items(
    cat_type: str,
    cat_id: str,
    genre: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
) -> List[Dict[str, Any]]:
    page = (skip // PAGE_SIZE) + 1

    if search:
        data = await search_moviesdrive_api(search, page=page)
        items: List[Dict[str, Any]] = []
        for hit in data.get("hits", []):
            doc = hit.get("document", {})
            slug = (doc.get("permalink") or "").strip("/")
            if not slug:
                continue
            title = doc.get("post_title", "Untitled")
            items.append(
                {
                    "id": "moviesdrive:" + slug,
                    "type": "series" if looks_like_series(title) else "movie",
                    "name": title,
                    "poster": absolute(doc.get("post_thumbnail", "")),
                    "posterShape": "poster",
                }
            )
        return items

    url = _catalog_url(cat_type, cat_id, genre, page)
    items = await cached_call(
        "cat:" + strip_base(url),
        lambda: _scrape_catalog(url),
        ttl=CATALOG_TTL,
        stale_ttl=CATALOG_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )
    return items or []


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
    name = title_tag.get_text(strip=True) if title_tag else slug.replace("-", " ").title()

    content = post_content(page_html)
    img_tag = content.find("img") if content else None
    poster = absolute(img_tag.get("src")) if img_tag else ""

    description = ""
    for p in (content.find_all("p") if content else []):
        txt = p.get_text(strip=True)
        if len(txt) > 80 and not any(
            word in txt.lower()
            for word in ("download", "link", "click here", "telegram", "join")
        ):
            description = txt
            break

    is_series = bool(media_type == "series" or re.search(r"season|s\d+|series", name, re.I))
    videos: List[Dict[str, Any]] = []

    if is_series:
        season_match = re.search(r"season\s*(\d+)|s(\d+)", name, re.I)
        season_num = (
            int(season_match.group(1) or season_match.group(2)) if season_match else 1
        )
        ep_count = await _episode_count(content, post_url, page_html)
        for ep in range(1, ep_count + 1):
            videos.append(
                {
                    "id": "moviesdrive:" + slug + ":" + str(season_num) + ":" + str(ep),
                    "title": "Tap " + str(ep) + " (Episode " + str(ep) + ")",
                    "season": season_num,
                    "episode": ep,
                    "released": "2026-01-01T00:00:00.000Z",
                }
            )

    meta_obj: Dict[str, Any] = {
        "id": item_id,
        "type": "series" if is_series else "movie",
        "name": name,
        "poster": poster,
        "background": poster,
        "description": description
        or ("Watch " + name + " on MoviesDrive in 4K UHD, 1080p, 720p."),
        "genres": ["Action", "HD", "Dual Audio"],
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

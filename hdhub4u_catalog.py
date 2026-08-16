"""
Catalog, metadata, and Cinemeta mapping layer for HDHub4u addon.
"""

import asyncio
import html as html_lib
import json
import logging
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

import hdhub4u_perf as perf
from hdhub4u_perf import (
    NEGATIVE_TTL,
    base_of,
    cached_call,
    fetch_json,
    make_soup,
    note_active_base,
    race_fetch_text,
)
import hdhub4u_resolver as resolver
from hdhub4u_resolver import (
    absolute,
    current_base,
    fetch_html,
    strip_base,
)

logger = logging.getLogger("hdhub4u_addon")

CINEMETA_BASE = "https://v3-cinemeta.strem.io"
CINEMETA_API = CINEMETA_BASE + "/meta"
CINEMETA_CATALOG = CINEMETA_BASE + "/catalog"
OPENSUBTITLES_BASE = "https://opensubtitles-v3.strem.io/subtitles/"

CATALOG_TTL = perf._env_int("HDH_CATALOG_TTL", 300)
CATALOG_STALE_TTL = perf._env_int("HDH_CATALOG_STALE_TTL", 1800)
SEARCH_TTL = perf._env_int("HDH_SEARCH_TTL", 600)
META_TTL = perf._env_int("HDH_META_TTL", 900)
META_STALE_TTL = perf._env_int("HDH_META_STALE_TTL", 7200)
CINEMETA_TTL = perf._env_int("HDH_CINEMETA_TTL", 3600)
IMDB_TTL = perf._env_int("HDH_IMDB_TTL", 86400)
PAGE_SIZE = perf._env_int("HDH_CATALOG_PAGE_SIZE", 24)

CATEGORIES_MAP = {
    "Phim Mới": "",
    "Bollywood": "bollywood-movies",
    "Hollywood": "hollywood-movies",
    "Hindi Dubbed": "hindi-dubbed",
    "South Hindi": "south-hindi-movies",
    "Web Series": "category/web-series",
    "Dual Audio": "dual-audio",
    "Action": "action-movies",
    "Adventure": "adventure",
    "Animation": "animated-movies",
    "Comedy": "comedy-movies",
    "Crime": "crime",
    "Drama": "drama",
    "Fantasy": "fantasy",
    "Horror": "horror-movies",
    "Romance": "romantic-movies",
    "Sci-Fi": "sci-fi",
    "Thriller": "thriller",
    "300MB": "300mb-movies",
    "18+": "adult",
}
GENRE_OPTIONS = list(CATEGORIES_MAP.keys())

SKIP_SLUG_WORDS = ("category", "tag", "contact", "dmca", "privacy", "how-to-download", "disclaimer")
SERIES_PATTERN = re.compile(r"season|s\d+|series|episodes?|ep\d+", re.I)


def looks_like_series(title: str, url: str) -> bool:
    return bool(SERIES_PATTERN.search(title) or SERIES_PATTERN.search(url))


def clean_title(title: str) -> str:
    t = title or ""
    # Strip any leading non-alphanumeric unicode icons (e.g. ≡, \ue02c, 🏠)
    t = re.sub(r"^[^\w\s]+", "", t).strip()
    t = re.sub(r"\((20\d\d|19\d\d)\)", r"\1", t)
    # Remove quality / codec / channel / episode noise tags
    t = re.sub(
        r"[\(\[\{]\s*(?:WEB-DL|WEBRip|BluRay|HDTC|DS4K|4K|1080p|720p|480p|HEVC|10Bit|x264|x265|Dual Audio|Hindi|English|Tamil|Telugu|Punjabi|ESubs?|Multi Audio|Full Movie|ALL Episodes|NF Series|PrimeVideo Series|HBO Series|JioHotstar Series|EP[\s\-]*\d+\s*Added|Without-ADs|HQ[/\-]Studio Dub)[^\)\]\}]*[\)\]\}]",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"\b(?:WEB-DL|WEBRip|BluRay|HDTC|DS4K|4K|1080p|720p|480p|HEVC|10Bit|x264|x265|Dual Audio|Hindi|English|Tamil|Telugu|Punjabi|ESubs?|Multi Audio|Full Movie|ALL Episodes|NF Series|PrimeVideo Series|HBO Series|JioHotstar Series)\b.*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"[\–\-\|]\s*(?:HDHub4u|Full Movie|Official|ALL Episodes|NF Series|PrimeVideo Series|HBO Series|JioHotstar Series).*", "", t, flags=re.I)
    t = re.sub(r"[\[\]\(\)\|\-–—]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------
# Scraping Items from HTML (Search & Catalog)
# ------------------------------------------------------------------
def _parse_post_items(html: str) -> List[Dict[str, Any]]:
    if not html:
        return []
    soup = make_soup(html)
    items: List[Dict[str, Any]] = []
    seen = set()

    # Select all article/movie cards
    cards = soup.select("li.recent-movies, article, .thumb, .post-item, .item, .recent-movie")
    if not cards:
        cards = soup.select(".entry-title a, h2 a, h3 a")

    for card in cards:
        a = card.find("a", href=True) if card.name != "a" else card
        if not a:
            continue
        href = a["href"]
        if href in seen:
            continue

        raw_title = a.get("title") or a.get_text(strip=True)
        if not raw_title:
            img_tag = card.find("img")
            if img_tag:
                raw_title = img_tag.get("alt") or img_tag.get("title", "")

        if not raw_title or len(raw_title) < 3:
            continue
        if any(w in href.lower() for w in SKIP_SLUG_WORDS):
            continue

        img_elem = card.find("img")
        poster = ""
        if img_elem:
            src = img_elem.get("src") or img_elem.get("data-src") or ""
            if src and not any(skip in src.lower() for skip in (".svg", "logo", "banner", "icon", "advert", "avatar", "sharethis", "telegram", "whatsapp")):
                poster = src

        full_url = absolute(href)
        slug = strip_base(full_url).strip("/")
        if not slug:
            continue

        is_series = looks_like_series(raw_title, href)
        item_type = "series" if is_series else "movie"
        cleaned_name = clean_title(raw_title) or raw_title

        seen.add(href)
        items.append({
            "id": f"hdhub4u:{slug}",
            "type": item_type,
            "name": cleaned_name,
            "poster": poster,
            "url": full_url,
            "slug": slug,
        })
    return items


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------
async def _scrape_search(query: str, page: int = 1) -> List[Dict[str, Any]]:
    clean_q = query.strip()
    if not clean_q:
        return []

    base = current_base()
    if page > 1:
        path = f"/page/{page}/?s={urllib.parse.quote(clean_q)}"
    else:
        path = f"/?s={urllib.parse.quote(clean_q)}"

    url = base + path
    html = await fetch_html(url)
    return _parse_post_items(html)


async def search_hdhub4u(query: str, page: int = 1) -> List[Dict[str, Any]]:
    return await cached_call(
        f"hdh_search:{query}:{page}",
        lambda: _scrape_search(query, page),
        ttl=SEARCH_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


# ------------------------------------------------------------------
# Catalog
# ------------------------------------------------------------------
async def _scrape_catalog(category: str, page: int = 1) -> List[Dict[str, Any]]:
    base = current_base()
    cat_slug = CATEGORIES_MAP.get(category, category)

    if not cat_slug:
        if page > 1:
            path = f"/page/{page}/"
        else:
            path = "/"
    else:
        if page > 1:
            path = f"/category/{cat_slug}/page/{page}/"
        else:
            path = f"/category/{cat_slug}/"

    url = base + path
    html = await fetch_html(url)
    return _parse_post_items(html)


async def get_catalog_items(category: str = "Phim Mới", skip: int = 0) -> List[Dict[str, Any]]:
    page = (skip // PAGE_SIZE) + 1
    return await cached_call(
        f"hdh_cat:{category}:{page}",
        lambda: _scrape_catalog(category, page),
        ttl=CATALOG_TTL,
        stale_ttl=CATALOG_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


# ------------------------------------------------------------------
# Metadata & Post Details
# ------------------------------------------------------------------
async def _scrape_meta(slug: str) -> Optional[Dict[str, Any]]:
    url = current_base() + "/" + slug.strip("/") + "/"
    html = await fetch_html(url)
    if not html:
        return None

    soup = make_soup(html)
    title_tag = soup.find("h1") or soup.find("title")
    raw_title = title_tag.get_text(strip=True) if title_tag else slug

    # Find IMDb ID if linked on post page
    imdb_id = None
    for a in soup.find_all("a", href=True):
        m = re.search(r"(tt\d{7,10})", a["href"])
        if m:
            imdb_id = m.group(1)
            break

    is_series = looks_like_series(raw_title, slug)
    item_type = "series" if is_series else "movie"

    # If IMDb ID exists, enrich with Cinemeta official metadata
    if imdb_id:
        cm_data = await fetch_json(f"{CINEMETA_API}/{item_type}/{imdb_id}.json", headers=perf.DEFAULT_HEADERS)
        if isinstance(cm_data, dict) and "meta" in cm_data:
            cm_meta = cm_data["meta"]
            raw_desc = cm_meta.get("description") or ""
            vi_desc = raw_desc
            if raw_desc:
                try:
                    from translation_service import translate_to_vietnamese
                    vi_desc = await translate_to_vietnamese(raw_desc)
                except Exception:
                    vi_desc = raw_desc

            meta_res: Dict[str, Any] = {
                "id": f"hdhub4u:{slug}",
                "type": item_type,
                "name": cm_meta.get("name") or clean_title(raw_title),
                "poster": cm_meta.get("poster") or "",
                "background": cm_meta.get("background") or "",
                "logo": cm_meta.get("logo") or "",
                "description": vi_desc or raw_desc,
                "releaseInfo": cm_meta.get("releaseInfo") or cm_meta.get("year", ""),
                "imdbRating": cm_meta.get("imdbRating", ""),
                "genres": cm_meta.get("genres", []),
                "imdb_id": imdb_id,
                "url": url,
            }
            if is_series:
                buttons = await resolver.resolve_all_download_buttons_from_post(url)
                episodes_seen = set()
                videos = []
                for b in buttons:
                    s = b.get("season") or 1
                    e = b.get("episode") or 1
                    se_key = f"{s}:{e}"
                    if se_key not in episodes_seen:
                        episodes_seen.add(se_key)
                        videos.append({
                            "id": f"hdhub4u:{slug}:{s}:{e}",
                            "title": f"Season {s} Episode {e}",
                            "season": s,
                            "episode": e,
                        })
                if videos:
                    videos.sort(key=lambda x: (x["season"], x["episode"]))
                    meta_res["videos"] = videos
            return meta_res

    # Fallback to local scraping
    poster = ""
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src and not any(skip in src.lower() for skip in (".svg", "logo", "banner", "icon", "advert", "avatar", "sharethis", "telegram", "whatsapp")):
            poster = src
            break

    # Extract clean synopsis
    desc = ""
    for header in soup.find_all(["h1", "h2", "h3", "h4", "span", "p"]):
        htxt = header.get_text(strip=True)
        if any(kw in htxt.lower() for kw in ("storyline", "story:", "plot:", "about movie", "overview", "synopsis")):
            for sib in header.next_siblings:
                if hasattr(sib, "get_text"):
                    st = sib.get_text(" ", strip=True)
                    if st and len(st) > 20:
                        st = re.sub(r"(Download\s+.*?|Review\s*:.*|Did you Like it.*|\bComments?\b.*|–\s*Review\s*:.*)", "", st, flags=re.I)
                        st = re.sub(r"^[^:]+:\s*", "", st)
                        desc = st.strip()
                        if len(desc) > 30:
                            break
            if desc:
                break

    if not desc:
        for p in soup.find_all("p"):
            pt = p.get_text(" ", strip=True)
            if 40 < len(pt) < 400 and not any(bad in pt.lower() for bad in ("avoid fake", "whatsapp", "how to download", "copyright", "click here", "telegram", "disclaimer", "all rights reserved")):
                pt = re.sub(r"(Download\s+.*?|Review\s*:.*|Did you Like it.*|\bComments?\b.*|–\s*Review\s*:.*)", "", pt, flags=re.I).strip()
                desc = pt
                break

    cleaned_name = clean_title(raw_title) or raw_title
    vi_desc = desc
    if desc:
        try:
            from translation_service import translate_to_vietnamese
            vi_desc = await translate_to_vietnamese(desc)
        except Exception:
            vi_desc = desc

    meta: Dict[str, Any] = {
        "id": f"hdhub4u:{slug}",
        "type": item_type,
        "name": cleaned_name,
        "poster": poster,
        "description": vi_desc or desc or cleaned_name,
        "imdb_id": imdb_id,
        "url": url,
    }

    if is_series:
        buttons = await resolver.resolve_all_download_buttons_from_post(url)
        # Build videos list for series
        episodes_seen = set()
        videos = []
        for b in buttons:
            s = b.get("season") or 1
            e = b.get("episode") or 1
            se_key = f"{s}:{e}"
            if se_key not in episodes_seen:
                episodes_seen.add(se_key)
                videos.append({
                    "id": f"hdhub4u:{slug}:{s}:{e}",
                    "title": f"Season {s} Episode {e}",
                    "season": s,
                    "episode": e,
                })
        if videos:
            videos.sort(key=lambda x: (x["season"], x["episode"]))
            meta["videos"] = videos

    return meta


async def get_meta_object(slug: str) -> Optional[Dict[str, Any]]:
    return await cached_call(
        f"hdh_meta:{slug}",
        lambda: _scrape_meta(slug),
        ttl=META_TTL,
        stale_ttl=META_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


# ------------------------------------------------------------------
# Cinemeta Title & IMDb Matching
# ------------------------------------------------------------------
async def _fetch_cinemeta_title(imdb_id: str, media_type: str = "movie") -> Optional[Dict[str, Any]]:
    url = f"{CINEMETA_API}/{media_type}/{imdb_id}.json"
    data = await fetch_json(url, headers=perf.DEFAULT_HEADERS)
    if isinstance(data, dict) and "meta" in data:
        m = data["meta"]
        return {
            "name": m.get("name", ""),
            "year": m.get("year", ""),
            "type": m.get("type", media_type),
        }
    return None


async def get_cinemeta_title(imdb_id: str, media_type: str = "movie") -> Optional[Dict[str, Any]]:
    return await cached_call(
        f"hdh_cinemeta:{imdb_id}:{media_type}",
        lambda: _fetch_cinemeta_title(imdb_id, media_type),
        ttl=CINEMETA_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


async def find_hdhub4u_for_imdb(imdb_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
    """Search HDHub4u using Cinemeta movie/series name and year."""
    info = await get_cinemeta_title(imdb_id, media_type)
    if not info or not info.get("name"):
        return []

    name = info["name"]
    year = str(info.get("year", ""))

    # Search with name
    results = await search_hdhub4u(name)
    if not results and " " in name:
        # Fallback search without special subtitle
        first_part = name.split(":")[0].split("-")[0].strip()
        if first_part and first_part != name:
            results = await search_hdhub4u(first_part)

    if not results:
        return []

    # Score and filter matching results
    clean_q = name.lower()
    matched = []
    for r in results:
        t_low = r["name"].lower()
        # Direct word overlap
        words = [w for w in re.findall(r"\w+", clean_q) if len(w) > 2]
        if words and all(w in t_low for w in words[:2]):
            matched.append(r)
        elif clean_q in t_low:
            matched.append(r)

    return matched or results

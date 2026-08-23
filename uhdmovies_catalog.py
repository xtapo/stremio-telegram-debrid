"""
Catalog, metadata, and Cinemeta mapping layer for UHDMovies addon.
"""

import asyncio
import html as html_lib
import json
import logging
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

import uhdmovies_perf as perf
from uhdmovies_perf import (
    NEGATIVE_TTL,
    base_of,
    cached_call,
    fetch_json,
    make_soup,
    note_active_base,
    race_fetch_text,
)
import uhdmovies_resolver as resolver
from uhdmovies_resolver import (
    absolute,
    current_base,
    fetch_html,
    strip_base,
)

logger = logging.getLogger("uhdmovies_addon")

CINEMETA_BASE = "https://v3-cinemeta.strem.io"
CINEMETA_API = CINEMETA_BASE + "/meta"
CINEMETA_CATALOG = CINEMETA_BASE + "/catalog"

CATALOG_TTL = perf._env_int("UHD_CATALOG_TTL", 300)
CATALOG_STALE_TTL = perf._env_int("UHD_CATALOG_STALE_TTL", 1800)
SEARCH_TTL = perf._env_int("UHD_SEARCH_TTL", 600)
META_TTL = perf._env_int("UHD_META_TTL", 900)
META_STALE_TTL = perf._env_int("UHD_META_STALE_TTL", 7200)
CINEMETA_TTL = perf._env_int("UHD_CINEMETA_TTL", 3600)
IMDB_TTL = perf._env_int("UHD_IMDB_TTL", 86400)
PAGE_SIZE = perf._env_int("UHD_CATALOG_PAGE_SIZE", 24)

CATEGORIES_MAP = {
    "Phim Mới": "movies",
    "4K HDR": "4k-hdr",
    "2160p HEVC": "2160p-hevc",
    "1080p 10Bit": "1080p-10bit",
    "Dual Audio": "movies/dual-audio-movies",
    "English Movies": "movies/english-movies",
    "IMAX": "imax",
    "TV Series": "tv-series",
    "Web Series": "web-series",
    "Collection": "collection",
}
GENRE_OPTIONS = list(CATEGORIES_MAP.keys())

SKIP_SLUG_WORDS = ("category", "tag", "contact", "dmca", "privacy", "how-to-download", "disclaimer")
SERIES_PATTERN = re.compile(r"season|s\d+|series|episodes?|ep\d+", re.I)


def looks_like_series(title: str, url: str) -> bool:
    return bool(SERIES_PATTERN.search(title) or SERIES_PATTERN.search(url))


def clean_title(title: str) -> str:
    t = title or ""
    # Strip leading Download and icons
    t = re.sub(r"^Download\s+", "", t, flags=re.I).strip()
    t = re.sub(r"^[^\w\s]+", "", t).strip()
    t = re.sub(r"\((20\d\d|19\d\d)\)", r"\1", t)
    t = re.sub(r"\[(?:Extended Cut|Added|Unrated|IMAX|REMASTERED|Director'?s Cut)[^\]]*\]", "", t, flags=re.I)
    t = re.sub(r"\{(?:Added|Hindi-English|English|Dual Audio|Multi Audio)[^\}]*\}", "", t, flags=re.I)
    # Remove quality / codec / channel / episode noise tags
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
    t = re.sub(r"[\–\-\|]\s*(?:UHDMovies|Full Movie|Official|ALL Episodes|Season \d+).*", "", t, flags=re.I)
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

    cards = soup.select("article.gridlove-post, article, .post-item, .item, div.post")
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
            if src and not any(skip in src.lower() for skip in (".svg", "logo", "banner", "icon", "advert", "avatar")):
                poster = src

        full_url = absolute(href)
        slug = strip_base(full_url).strip("/")
        if not slug:
            continue

        is_series = looks_like_series(raw_title, href)
        item_type = "series" if is_series else "movie"
        cleaned_name = clean_title(raw_title) or raw_title

        # Year match
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
        year = int(year_match.group(1)) if year_match else None

        seen.add(href)
        items.append({
            "id": f"uhdmovies:{slug}",
            "type": item_type,
            "name": cleaned_name,
            "raw_title": raw_title,
            "poster": poster,
            "year": year,
            "url": full_url,
            "slug": slug,
        })
    return items


# ------------------------------------------------------------------
# Catalog Fetching
# ------------------------------------------------------------------
async def get_category_page(category_slug: str, page: int = 1) -> List[Dict[str, Any]]:
    key = f"uhd:cat:{category_slug}:{page}"

    async def _fetch():
        base = current_base()
        if not category_slug or category_slug in ("movies", "home"):
            url = f"{base}/movies/page/{page}/" if page > 1 else f"{base}/movies/"
        else:
            cat_clean = category_slug.strip("/")
            url = f"{base}/{cat_clean}/page/{page}/" if page > 1 else f"{base}/{cat_clean}/"

        html = await fetch_html(url, race=True)
        if not html and page == 1 and not category_slug:
            # Fallback to root home
            html = await fetch_html(f"{base}/", race=True)
        return _parse_post_items(html)

    return await cached_call(
        key, _fetch, ttl=CATALOG_TTL, stale_ttl=CATALOG_STALE_TTL, negative_ttl=NEGATIVE_TTL
    ) or []


async def search_uhdmovies(query: str, page: int = 1) -> List[Dict[str, Any]]:
    if not query:
        return []
    clean_q = urllib.parse.quote(query.strip())
    key = f"uhd:search:{clean_q}:{page}"

    async def _fetch():
        base = current_base()
        url = f"{base}/search/{clean_q}/page/{page}/" if page > 1 else f"{base}/search/{clean_q}/"
        html = await fetch_html(url, race=True)
        return _parse_post_items(html)

    return await cached_call(
        key, _fetch, ttl=SEARCH_TTL, stale_ttl=CATALOG_STALE_TTL, negative_ttl=NEGATIVE_TTL
    ) or []


# ------------------------------------------------------------------
# Cinemeta Mapping & IMDb Bridge
# ------------------------------------------------------------------
async def get_cinemeta_meta(type_: str, imdb_id: str) -> Optional[Dict[str, Any]]:
    key = f"uhd:cinemeta:{type_}:{imdb_id}"

    async def _fetch():
        url = f"{CINEMETA_API}/{type_}/{imdb_id}.json"
        data = await fetch_json(url, timeout=6.0)
        return data.get("meta") if isinstance(data, dict) else None

    return await cached_call(key, _fetch, ttl=CINEMETA_TTL, negative_ttl=NEGATIVE_TTL)


async def find_uhdmovies_for_imdb(
    imdb_id: str,
    title: Optional[str] = None,
    year: Optional[int] = None,
    is_series: bool = False,
) -> List[Dict[str, Any]]:
    """Match IMDb ID to the best corresponding UHDMovies post items (ranked)."""
    if not imdb_id:
        return []

    key = f"uhd:imdb_map:{imdb_id}"
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

    # Search UHDMovies for title
    search_results = await search_uhdmovies(title, page=1)
    if not search_results:
        # Try simplified query without punctuation
        simplified = re.sub(r"[^\w\s]", " ", title).strip()
        if simplified != title:
            search_results = await search_uhdmovies(simplified, page=1)

    if not search_results:
        perf.set_cached(key, [], ttl=NEGATIVE_TTL)
        return []

    # Score and rank all matches
    scored_items: List[Tuple[int, Dict[str, Any]]] = []
    target_clean = clean_title(title).lower()

    for item in search_results:
        item_name = item.get("name", "").lower()
        score = 0
        if target_clean in item_name or item_name in target_clean:
            score += 50

        # Exact word match
        target_words = set(target_clean.split())
        item_words = set(item_name.split())
        common = target_words.intersection(item_words)
        score += len(common) * 10

        # Year match
        item_year = item.get("year")
        if year and item_year:
            if abs(year - item_year) <= 1:
                score += 30
            else:
                score -= 20

        # Series / Movie type alignment
        if is_series and item.get("type") == "series":
            score += 25
        elif not is_series and item.get("type") == "movie":
            score += 25

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
    key = f"uhd:meta:{clean_slug}"
    logger.info("get_meta_for_slug slug=%s, post_url=%s", clean_slug, post_url)

    async def _fetch():
        html = await resolver.get_post_page(post_url)
        logger.info("get_meta_for_slug fetched html len=%s", len(html) if html else "None")
        if not html:
            return None

        soup = make_soup(html)
        title_tag = soup.select_one("h1.entry-title, h1")
        raw_title = title_tag.get_text(strip=True) if title_tag else clean_slug.replace("-", " ").title()
        cleaned_title = clean_title(raw_title)

        year_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
        year = int(year_m.group(1)) if year_m else None

        img_tag = soup.select_one(".entry-content img, article img")
        poster = img_tag.get("src") or img_tag.get("data-src") if img_tag else ""

        # Description
        desc_p = soup.select_one(".entry-content p")
        description = desc_p.get_text(strip=True) if desc_p else f"{cleaned_title} on UHDMovies"

        # Genres
        genres = []
        for cat_a in soup.select(".entry-category a, a[rel='category tag']"):
            t = cat_a.get_text(strip=True)
            if t and t not in genres and not any(w in t.lower() for w in ("1080p", "2160p", "4k", "hevc", "movies")):
                genres.append(t)

        meta = {
            "id": f"uhdmovies:{clean_slug}",
            "type": item_type,
            "name": cleaned_title,
            "poster": poster,
            "background": poster,
            "description": description,
            "genres": genres or ["Action", "Adventure"],
            "year": year,
            "url": post_url,
        }

        # If series, parse episodes
        if item_type == "series" or looks_like_series(raw_title, post_url):
            meta["type"] = "series"
            videos = []
            candidates = resolver.parse_post_candidates(html)
            ep_dict: Dict[int, Dict[str, Any]] = {}
            for c in candidates:
                ep = c.get("episode")
                if ep is not None:
                    if ep not in ep_dict:
                        ep_dict[ep] = {
                            "id": f"uhdmovies:{clean_slug}:1:{ep}",
                            "title": f"Episode {ep}",
                            "season": c.get("season") or 1,
                            "episode": ep,
                            "released": f"{year or 2024}-01-01T00:00:00.000Z",
                        }
            for ep_num in sorted(ep_dict.keys()):
                videos.append(ep_dict[ep_num])
            if videos:
                meta["videos"] = videos

        return meta

    return await cached_call(key, _fetch, ttl=META_TTL, stale_ttl=META_STALE_TTL, negative_ttl=NEGATIVE_TTL)

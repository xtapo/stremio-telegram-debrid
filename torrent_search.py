import httpx
import logging
import urllib.parse
import re
from config import Config

logger = logging.getLogger("torrent_search")

async def search_torrents(query: str, imdb_id: str = None) -> list:
    """
    Search for torrents using Jackett, Prowlarr, or fallback APIs (YTS, EZTV, SolidTorrents).
    Returns a list of dicts: {
        "title": str,
        "magnet": str,  # magnet link or torrent file URL
        "size": int,
        "seeders": int,
        "leechers": int,
        "source": str
    }
    """
    results = []
    
    # 1. Try Prowlarr
    prowlarr_url = getattr(Config, "PROWLARR_URL", "")
    prowlarr_key = getattr(Config, "PROWLARR_API_KEY", "")
    if prowlarr_url and prowlarr_key:
        try:
            p_res = await _search_prowlarr(prowlarr_url, prowlarr_key, query)
            if p_res:
                results.extend(p_res)
        except Exception as e:
            logger.error(f"Prowlarr search failed: {e}")

    # 2. Try Jackett
    jackett_url = getattr(Config, "JACKETT_URL", "")
    jackett_key = getattr(Config, "JACKETT_API_KEY", "")
    if jackett_url and jackett_key:
        try:
            j_res = await _search_jackett(jackett_url, jackett_key, query)
            if j_res:
                results.extend(j_res)
        except Exception as e:
            logger.error(f"Jackett search failed: {e}")

    # If we got results from Jackett/Prowlarr, we can still fetch from YTS/EZTV for guaranteed matching,
    # or if we have no custom indexers, we query public APIs.
    
    # 3. YTS (Movies only)
    if imdb_id:
        try:
            yts_res = await _search_yts(imdb_id)
            if yts_res:
                results.extend(yts_res)
        except Exception as e:
            logger.error(f"YTS search failed: {e}")
            
    # 4. EZTV (Series/TV only)
    if imdb_id:
        try:
            eztv_res = await _search_eztv(imdb_id)
            if eztv_res:
                results.extend(eztv_res)
        except Exception as e:
            logger.error(f"EZTV search failed: {e}")

    # 5. Fallback SolidTorrents (general search)
    # Only run if we don't have enough results yet to save API calls
    if len(results) < 5:
        try:
            st_res = await _search_solidtorrents(query)
            if st_res:
                results.extend(st_res)
        except Exception as e:
            logger.error(f"SolidTorrents search failed: {e}")

    # Deduplicate results by magnet link or infohash
    seen_magnets = set()
    deduped = []
    for item in results:
        mag = item["magnet"]
        # Extract infohash to normalize magnet links
        infohash = _extract_infohash(mag)
        key = infohash if infohash else mag.lower()
        if key not in seen_magnets:
            seen_magnets.add(key)
            deduped.append(item)
            
    # Sort by seeders descending
    deduped.sort(key=lambda x: x["seeders"], reverse=True)
    
    return deduped[:Config.MAX_TORRENT_RESULTS]

def _extract_infohash(magnet: str) -> str:
    if not magnet:
        return ""
    m = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet)
    if m:
        return m.group(1).lower()
    return ""

async def _search_prowlarr(url: str, api_key: str, query: str) -> list:
    endpoint = f"{url.rstrip('/')}/api/v1/search"
    params = {
        "apikey": api_key,
        "query": query,
        "categories": [2000, 5000] # Movies & TV
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(endpoint, params=params)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for item in data:
            magnet = item.get("magnetUrl")
            download_url = item.get("downloadUrl")
            link = magnet or download_url
            if not link:
                continue
            results.append({
                "title": item.get("title", "Unknown"),
                "magnet": link,
                "size": item.get("size", 0),
                "seeders": item.get("seeders", 0),
                "leechers": item.get("leechers", 0),
                "source": f"Prowlarr ({item.get('indexer', 'Unknown')})"
            })
        return results

async def _search_jackett(url: str, api_key: str, query: str) -> list:
    endpoint = f"{url.rstrip('/')}/api/v2.0/indexers/all/results"
    params = {
        "apikey": api_key,
        "Query": query,
        "Category[]": [2000, 5000]
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(endpoint, params=params)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for item in data.get("Results", []):
            magnet = item.get("MagnetUri")
            torrent_link = item.get("Link")
            link = magnet or torrent_link
            if not link:
                continue
            results.append({
                "title": item.get("Title", "Unknown"),
                "magnet": link,
                "size": item.get("Size", 0),
                "seeders": item.get("Seeders", 0),
                "leechers": max(0, item.get("Peers", 0) - item.get("Seeders", 0)),
                "source": f"Jackett ({item.get('Tracker', 'Unknown')})"
            })
        return results

async def _search_yts(imdb_id: str) -> list:
    url = f"https://yts.mx/api/v2/list_movies.json?query_term={imdb_id}"
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()
        movie_data = data.get("data", {})
        if not movie_data or movie_data.get("movie_count", 0) == 0:
            return []
        
        results = []
        movies = movie_data.get("movies", [])
        for m in movies:
            title = m.get("title_long") or m.get("title")
            for t in m.get("torrents", []):
                infohash = t.get("hash")
                if not infohash:
                    continue
                quality = t.get("quality")
                t_type = t.get("type")
                size = t.get("size_bytes", 0)
                
                trackers = [
                    "udp://open.demonii.com:1337/announce",
                    "udp://tracker.coppersurfer.tk:6969/announce",
                    "udp://tracker.leechers-paradise.org:6969/announce",
                    "udp://open.stealth.si:80/announce",
                    "udp://tracker.coppersurfer.tk:6969",
                    "udp://glotorrents.pw:6969/announce",
                    "udp://tracker.opentrackr.org:1337/announce"
                ]
                tr_params = "&".join(f"tr={urllib.parse.quote(x)}" for x in trackers)
                dn = f"{title} [{quality}] [{t_type}]"
                magnet = f"magnet:?xt=urn:btih:{infohash}&dn={urllib.parse.quote(dn)}&{tr_params}"
                
                results.append({
                    "title": dn,
                    "magnet": magnet,
                    "size": size,
                    "seeders": t.get("seeds", 0),
                    "leechers": t.get("peers", 0),
                    "source": "YTS"
                })
        return results

async def _search_eztv(imdb_id: str) -> list:
    clean_id = imdb_id.replace("tt", "").strip()
    if not clean_id.isdigit():
        return []
        
    url = f"https://eztv.re/api/get-torrents?imdb_id={clean_id}"
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()
        torrents = data.get("torrents", [])
        if not torrents:
            return []
            
        results = []
        for t in torrents:
            magnet = t.get("magnet_url")
            if not magnet:
                continue
            title = t.get("filename") or t.get("title") or "EZTV Torrent"
            results.append({
                "title": title,
                "magnet": magnet,
                "size": int(t.get("size_bytes", 0)),
                "seeders": int(t.get("seeds", 0)),
                "leechers": int(t.get("peers", 0)),
                "source": "EZTV"
            })
        return results

async def _search_solidtorrents(query: str) -> list:
    url = f"https://solidtorrents.net/api/v1/search?q={urllib.parse.quote(query)}&category=video"
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for item in data.get("results", []):
            magnet = item.get("magnet")
            if not magnet:
                continue
            results.append({
                "title": item.get("title", "Unknown"),
                "magnet": magnet,
                "size": item.get("size", 0),
                "seeders": item.get("swarm", {}).get("seeders", 0),
                "leechers": item.get("swarm", {}).get("leechers", 0),
                "source": "SolidTorrents"
            })
        return results

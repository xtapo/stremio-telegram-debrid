import logging
import urllib.parse
import re
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, Response
import httpx

# Try importing BeautifulSoup if available, otherwise use regex fallback
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

logger = logging.getLogger("hhpanda_addon")

hhpanda_router = APIRouter(prefix="", tags=["hhpanda"])

HHPANDA_BASE = "https://hhpanda.st"
HHPANDA_API_BASE = "https://hhpanda.st/wp-json/wp/v2"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://hhpanda.st/"
}

GENRES_MAP = {
    "Tu Tiên": "tu-tien",
    "Kiếm Hiệp": "kiem-hiep",
    "Cổ Trang": "co-trang",
    "Huyền Huyễn": "huyen-huyen",
    "Khoa Huyễn": "khoa-huyen",
    "Kỳ Ảo": "ky-ao",
    "Huyền Nghi": "huyen-nghi",
    "Cạnh Kỹ": "canh-ky",
    "Dã Sử": "da-su",
    "Đô Thị": "do-thi",
    "Đồng Nhân": "dong-nhan"
}

GENRE_OPTIONS = list(GENRES_MAP.keys())

MANIFEST = {
    "id": "com.stremio.hhpanda.addon",
    "version": "1.0.0",
    "name": "HHPanda - Hoạt Hình 3D 4K",
    "description": "Xem Phim Hoạt Hình 3D Trung Quốc Thuyết Minh & VietSub 4K sắc nét nhất từ HHPanda (hhpanda.st)",
    "resources": [
        "catalog",
        {
            "name": "meta",
            "types": ["series", "movie"],
            "idPrefixes": ["hhpanda:"]
        },
        {
            "name": "stream",
            "types": ["series", "movie"],
            "idPrefixes": ["hhpanda:"]
        }
    ],
    "types": ["series", "movie"],
    "catalogs": [
        {
            "type": "series",
            "id": "hhpanda_moi_cap_nhat",
            "name": "HHPanda - Mới Cập Nhật",
            "extra": [
                {"name": "search", "isRequired": False},
                {"name": "genre", "options": GENRE_OPTIONS, "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "hhpanda_the_loai",
            "name": "HHPanda - Thể Loại",
            "extra": [
                {"name": "genre", "options": GENRE_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "hhpanda_hoan_thanh",
            "name": "HHPanda - Phim Hoàn Thành",
            "extra": [
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "hhpanda_top_xem_nhieu",
            "name": "HHPanda - Top Xem Nhiều",
            "extra": [
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        }
    ]
}

@hhpanda_router.get("/hhpanda/manifest.json")
@hhpanda_router.get("/manifest.json")
async def get_manifest():
    return JSONResponse(MANIFEST)


# ------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------

def parse_movie_items_from_html(html_text: str) -> List[Dict[str, Any]]:
    """Parse list of movies from HTML page."""
    if BeautifulSoup:
        soup = BeautifulSoup(html_text, "html.parser")
        items = []
        seen_ids = set()

        for el in soup.select("article, .halim-item, .top-slide"):
            a_tag = el.select_one("a")
            if not a_tag:
                continue

            href = a_tag.get("href", "")
            if not href or href == "#":
                continue

            href_clean = href.rstrip("/").split("/")[-1]
            if not href_clean or href_clean in seen_ids:
                continue
            seen_ids.add(href_clean)

            title_el = el.select_one(".entry-title, .title, .halim-trending-title-text, h2, h3")
            title = title_el.get_text(strip=True) if title_el else a_tag.get("title", href_clean)

            img_el = el.select_one("img")
            poster = ""
            if img_el:
                poster = img_el.get("src") or img_el.get("data-src") or img_el.get("data-original", "")

            eps_el = el.select_one(".episode, .halim-episode, .halim-post-quality, .halim-label")
            badge = eps_el.get_text(strip=True) if eps_el else ""

            items.append({
                "id": f"hhpanda:{href_clean}",
                "type": "series",
                "name": title,
                "poster": poster,
                "description": f"{title} {(' - ' + badge) if badge else ''}".strip(),
                "genres": ["Hoạt Hình 3D"]
            })

        return items

    # Pure Regex Fallback
    items = []
    seen_ids = set()
    matches = re.findall(r'<a[^>]+href=["\']https?://hhpanda\.st/([^"\']+)["\'][^>]*title=["\']([^"\']+)["\'][^>]*>', html_text)
    
    for slug, title in matches:
        slug = slug.strip("/")
        if not slug or slug in seen_ids or any(k in slug for k in ["the-loai", "country", "showtimes", "page", "account"]):
            continue
        seen_ids.add(slug)
        items.append({
            "id": f"hhpanda:{slug}",
            "type": "series",
            "name": title,
            "poster": "https://hhpanda.st/wp-content/uploads/default-poster.jpg",
            "description": title,
            "genres": ["Hoạt Hình 3D"]
        })
    return items


async def fetch_wp_posts(page: int = 1, search: str = "") -> List[Dict[str, Any]]:
    """Fetch movies via WP REST API if possible."""
    url = f"{HHPANDA_API_BASE}/posts?per_page=24&page={page}"
    if search:
        url += f"&search={urllib.parse.quote(search)}"
    
    async with httpx.AsyncClient(timeout=10, headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(url)
        if r.status_code != 200:
            return []
        
        data = r.json()
        metas = []
        for post in data:
            slug = post.get("slug")
            if not slug:
                continue
            title = post.get("title", {}).get("rendered", slug)
            meta_box = post.get("_halim_metabox_options", {})
            badge = meta_box.get("halim_episode", "")
            
            poster = "https://hhpanda.st/wp-content/uploads/default-poster.jpg"
            if post.get("yoast_head_json", {}).get("og_image"):
                og_imgs = post.get("yoast_head_json", {}).get("og_image")
                if isinstance(og_imgs, list) and len(og_imgs) > 0:
                    poster = og_imgs[0].get("url", poster)

            metas.append({
                "id": f"hhpanda:{slug}",
                "type": "series",
                "name": title,
                "poster": poster,
                "description": f"{title} {(' - ' + badge) if badge else ''}".strip(),
                "genres": ["Hoạt Hình 3D"]
            })
        return metas


# ------------------------------------------------------------------
# CATALOG HANDLER
# ------------------------------------------------------------------

@hhpanda_router.get("/hhpanda/catalog/{type}/{catalog_id}.json")
@hhpanda_router.get("/catalog/{type}/{catalog_id}.json")
@hhpanda_router.get("/hhpanda/catalog/{type}/{catalog_id}/{extra}.json")
@hhpanda_router.get("/catalog/{type}/{catalog_id}/{extra}.json")
async def get_catalog(
    type: str,
    catalog_id: str,
    extra: Optional[str] = None,
    search: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    skip: Optional[int] = Query(0)
):
    if extra:
        for item in extra.split("&"):
            if "=" in item:
                k, v = item.split("=", 1)
                v = urllib.parse.unquote(v)
                if k == "search":
                    search = v
                elif k == "genre":
                    genre = v
                elif k == "skip":
                    try:
                        skip = int(v)
                    except ValueError:
                        pass

    page = (skip // 24) + 1 if skip else 1

    # 1. Search Query
    if search:
        search_url = f"{HHPANDA_BASE}/page/{page}?s={urllib.parse.quote(search)}" if page > 1 else f"{HHPANDA_BASE}/?s={urllib.parse.quote(search)}"
        async with httpx.AsyncClient(timeout=10, headers=HEADERS, follow_redirects=True) as client:
            r = await client.get(search_url)
            if r.status_code == 200:
                metas = parse_movie_items_from_html(r.text)
                return JSONResponse({"metas": metas})
            else:
                metas = await fetch_wp_posts(page=page, search=search)
                return JSONResponse({"metas": metas})

    # 2. Genre Query
    if genre and genre in GENRES_MAP:
        genre_slug = GENRES_MAP[genre]
        genre_url = f"{HHPANDA_BASE}/the-loai/{genre_slug}/page/{page}" if page > 1 else f"{HHPANDA_BASE}/the-loai/{genre_slug}"
        async with httpx.AsyncClient(timeout=10, headers=HEADERS, follow_redirects=True) as client:
            r = await client.get(genre_url)
            if r.status_code == 200:
                metas = parse_movie_items_from_html(r.text)
                return JSONResponse({"metas": metas})

    # 3. Catalog Specific URLs
    target_url = f"{HHPANDA_BASE}/moi-cap-nhat/page/{page}" if page > 1 else f"{HHPANDA_BASE}/moi-cap-nhat"
    
    if catalog_id == "hhpanda_hoan_thanh":
        target_url = f"{HHPANDA_BASE}/hoan-thanh/page/{page}" if page > 1 else f"{HHPANDA_BASE}/hoan-thanh"
    elif catalog_id == "hhpanda_top_xem_nhieu":
        target_url = f"{HHPANDA_BASE}/most-viewed/page/{page}" if page > 1 else f"{HHPANDA_BASE}/most-viewed"

    async with httpx.AsyncClient(timeout=10, headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(target_url)
        if r.status_code == 200:
            metas = parse_movie_items_from_html(r.text)
            if metas:
                return JSONResponse({"metas": metas})

    metas = await fetch_wp_posts(page=page)
    return JSONResponse({"metas": metas})


# ------------------------------------------------------------------
# META HANDLER
# ------------------------------------------------------------------

@hhpanda_router.get("/hhpanda/meta/{type}/{id}.json")
@hhpanda_router.get("/meta/{type}/{id}.json")
async def get_meta(type: str, id: str):
    if not id.startswith("hhpanda:"):
        raise HTTPException(status_code=404, detail="Invalid HHPanda ID format")

    slug = id.replace("hhpanda:", "")
    url = f"{HHPANDA_BASE}/{slug}"

    async with httpx.AsyncClient(timeout=12, headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(status_code=404, detail="Movie not found on HHPanda")

        html_text = r.text

        title = slug
        poster = ""
        description = ""
        rating = None

        if BeautifulSoup:
            soup = BeautifulSoup(html_text, "html.parser")

            title_el = soup.select_one(".entry-title, h1.title, .film-title")
            title = title_el.get_text(strip=True) if title_el else slug

            og_img = soup.find("meta", property="og:image")
            poster = og_img["content"] if og_img and og_img.get("content") else ""

            og_desc = soup.find("meta", property="og:description")
            description = og_desc["content"] if og_desc and og_desc.get("content") else ""
            if not description:
                desc_el = soup.select_one(".entry-content, .film-content, .description")
                if desc_el:
                    description = desc_el.get_text(strip=True)

            rating_el = soup.select_one(".halim-trending-rating-value, .rating-val")
            rating = rating_el.get_text(strip=True) if rating_el else None
        else:
            og_t = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html_text)
            og_i = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html_text)
            og_d = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html_text)
            if og_t: title = og_t.group(1)
            if og_i: poster = og_i.group(1)
            if og_d: description = og_d.group(1)

        # Parse episode links deduplicated by (post_id, data_ep)
        episodes_dict = {}

        if BeautifulSoup:
            soup = BeautifulSoup(html_text, "html.parser")
            ep_elements = soup.select(".halim-episode a")
            for idx, a in enumerate(ep_elements):
                ep_title = a.get_text(strip=True)
                post_id = a.get("data-post-id", "")
                data_ep = a.get("data-ep", "")
                if not post_id or not data_ep:
                    continue
                ep_match = re.search(r'\d+', ep_title)
                ep_num = int(ep_match.group(0)) if ep_match else (idx + 1)
                key = (post_id, data_ep)
                if key not in episodes_dict:
                    episodes_dict[key] = {
                        "id": f"hhpanda:{slug}:{post_id}:{data_ep}",
                        "title": f"Tập {ep_num} (Thuyết Minh & VietSub)",
                        "episode": ep_num,
                        "season": 1,
                        "released": "2026-01-01T00:00:00.000Z"
                    }
        else:
            ep_matches = re.findall(
                r'data-post-id=["\'](\d+)["\'][\s\S]*?data-ep=["\']([^"\']+)["\'][\s\S]*?>(.*?)</a>',
                html_text
            )
            for idx, (post_id, data_ep, ep_title_raw) in enumerate(ep_matches):
                ep_title = re.sub(r'<[^>]+>', '', ep_title_raw).strip()
                ep_match = re.search(r'\d+', ep_title)
                ep_num = int(ep_match.group(0)) if ep_match else (idx + 1)
                key = (post_id, data_ep)
                if key not in episodes_dict:
                    episodes_dict[key] = {
                        "id": f"hhpanda:{slug}:{post_id}:{data_ep}",
                        "title": f"Tập {ep_num} (Thuyết Minh & VietSub)",
                        "episode": ep_num,
                        "season": 1,
                        "released": "2026-01-01T00:00:00.000Z"
                    }

        videos = list(episodes_dict.values())
        videos.sort(key=lambda v: v["episode"])

        meta = {
            "id": id,
            "type": type,
            "name": title,
            "poster": poster,
            "background": poster,
            "description": f"✨ Chất lượng: 4K Ultra HD / 2160p (Thuyết Minh & VietSub)\n\n{description}".strip(),
            "genres": ["Hoạt Hình 3D 4K", "Thuyết Minh", "VietSub", "4K Ultra HD"],
            "imdbRating": rating,
            "videos": videos
        }

        return JSONResponse({"meta": meta})


# ------------------------------------------------------------------
# STREAM HANDLER
# ------------------------------------------------------------------

async def fetch_single_stream(client: httpx.AsyncClient, player_url: str, post_id: str, data_ep: str, sv: str, sv_label: str, sv_type: str, type_label: str, base_host: str, slug: str) -> List[Dict[str, Any]]:
    """Fetch single stream option (sv=1/2, type=pro/tiktik) from HHPanda player.php."""
    results = []
    try:
        r = await client.get(player_url, params={
            "action": "dox_ajax_player",
            "post_id": post_id,
            "chapter_st": data_ep,
            "sv": sv,
            "type": sv_type
        })
        if r.status_code == 200:
            iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', r.text)
            if iframe_match:
                iframe_src = iframe_match.group(1)
                if "not-found" not in iframe_src:
                    proxy_url = f"{base_host}/hhpanda/player_proxy?src={urllib.parse.quote(iframe_src)}"
                    
                    badge_icon = "🎙️ [Thuyết Minh]" if sv == "2" else "💬 [VietSub]"
                    sv_title = "4K Ultra HD V2" if sv_type == "pro" else "4K Ultra HD V1"
                    
                    results.append({
                        "name": "HHPanda 4K Proxy",
                        "title": f"🌐 {badge_icon} HHPanda {sv_title} (Player Proxy)",
                        "externalUrl": proxy_url
                    })
    except Exception as e:
        logger.warning(f"Error fetching stream sv={sv} type={sv_type}: {e}")
    return results


@hhpanda_router.get("/hhpanda/stream/{type}/{id}.json")
@hhpanda_router.get("/stream/{type}/{id}.json")
async def get_stream(request: Request, type: str, id: str):
    if not id.startswith("hhpanda:"):
        raise HTTPException(status_code=404, detail="Invalid HHPanda Stream ID")

    parts = id.split(":")
    if len(parts) < 4:
        raise HTTPException(status_code=400, detail="Invalid stream parameter components")

    slug = parts[1]
    post_id = parts[2]
    data_ep = parts[3]

    base_host = str(request.base_url).rstrip("/")
    player_url = f"{HHPANDA_BASE}/player/player.php"

    streams = [
        {
            "name": "🎙️ Thuyết Minh 4K",
            "title": "🌐 Xem trực tiếp Thuyết Minh 4K trên HHPanda.st",
            "externalUrl": f"{HHPANDA_BASE}/watch-{slug}/{data_ep}-sv2.html"
        },
        {
            "name": "💬 VietSub 4K",
            "title": "🌐 Xem trực tiếp VietSub 4K trên HHPanda.st",
            "externalUrl": f"{HHPANDA_BASE}/watch-{slug}/{data_ep}-sv1.html"
        }
    ]

    tasks = []
    async with httpx.AsyncClient(timeout=10, headers=HEADERS, follow_redirects=True) as client:
        tasks.append(fetch_single_stream(client, player_url, post_id, data_ep, "2", "Thuyết Minh", "pro", "1080P V2", base_host, slug))
        tasks.append(fetch_single_stream(client, player_url, post_id, data_ep, "2", "Thuyết Minh", "tiktik", "1080P V1", base_host, slug))
        tasks.append(fetch_single_stream(client, player_url, post_id, data_ep, "1", "VietSub", "pro", "1080P V2", base_host, slug))
        tasks.append(fetch_single_stream(client, player_url, post_id, data_ep, "1", "VietSub", "tiktik", "1080P V1", base_host, slug))

        fetched_results = await asyncio.gather(*tasks)

    for res_list in fetched_results:
        streams.extend(res_list)

    return JSONResponse({"streams": streams})


# ------------------------------------------------------------------
# STREAMFREE BACKEND PROXY (Bypass Referer & CORS)
# ------------------------------------------------------------------

@hhpanda_router.get("/hhpanda/streamfree_proxy")
@hhpanda_router.post("/hhpanda/streamfree_proxy")
@hhpanda_router.get("/streamfree_proxy")
@hhpanda_router.post("/streamfree_proxy")
async def streamfree_proxy(request: Request, path: str):
    """Proxy all API/asset requests from streamfree.vip with valid Referer."""
    target_url = urllib.parse.unquote(path)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://hhpanda.st/",
        "Origin": "https://streamfree.vip"
    }
    
    method = request.method
    body = await request.body()
    
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            r = await client.request(method, target_url, content=body)
            
            response_headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
            if "content-type" in r.headers:
                response_headers["content-type"] = r.headers["content-type"]

            return Response(content=r.content, status_code=r.status_code, headers=response_headers)
    except Exception as e:
        logger.warning(f"Error in streamfree_proxy target {target_url}: {e}")
        return Response(content=b"Proxy Error", status_code=500)


# ------------------------------------------------------------------
# PLAYER PROXY HTML WRAPPER & EMBED FRAME
# ------------------------------------------------------------------

@hhpanda_router.get("/hhpanda/player_proxy")
@hhpanda_router.get("/player_proxy")
async def player_proxy(request: Request, src: str):
    """Outer container HTML embedding proxy frame."""
    base_host = str(request.base_url).rstrip("/")
    embed_frame_url = f"{base_host}/hhpanda/embed_frame?src={urllib.parse.quote(src)}"

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HHPanda Player</title>
    <style>
        html, body {{
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            background-color: #000;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        iframe {{
            width: 100%;
            height: 100%;
            border: none;
        }}
    </style>
</head>
<body>
    <iframe src="{embed_frame_url}" 
            allowfullscreen="true" 
            webkitallowfullscreen="true" 
            mozallowfullscreen="true" 
            allow="autoplay; fullscreen; encrypted-media">
    </iframe>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@hhpanda_router.get("/hhpanda/embed_frame")
@hhpanda_router.get("/embed_frame")
async def embed_frame(request: Request, src: str):
    """Inner iframe content server-side fetched with Referer, DevTools Bypass & Document.Referer Patch."""
    iframe_src = urllib.parse.unquote(src)
    base_host = str(request.base_url).rstrip("/")
    proxy_endpoint = f"{base_host}/hhpanda/streamfree_proxy?path="

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://hhpanda.st/"
    }

    try:
        async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as client:
            r = await client.get(iframe_src)
            if r.status_code == 200:
                html = r.text
                domain_match = re.match(r'(https?://[^/]+)', iframe_src)
                base_domain = domain_match.group(1) if domain_match else "https://streamfree.vip"
                
                patch_script = f"""<base href="{base_domain}/">
<script>
(function() {{
    var noop = function() {{}};
    try {{
        window.console.log = noop;
        window.console.clear = noop;
        window.console.table = noop;
        window.console.warn = noop;
        window.console.error = noop;
        window.console.debug = noop;
        window.console.info = noop;
    }} catch(e) {{}}

    try {{
        Object.defineProperty(window, 'outerWidth', {{ get: function() {{ return window.innerWidth; }} }});
        Object.defineProperty(window, 'outerHeight', {{ get: function() {{ return window.innerHeight; }} }});
    }} catch(e) {{}}

    try {{
        Object.defineProperty(document, 'referrer', {{
            get: function() {{ return 'https://hhpanda.st/'; }}
        }});
    }} catch(e) {{}}

    var PROXY_ENDPOINT = "{proxy_endpoint}";
    var BASE_DOMAIN = "{base_domain}";

    function rewriteUrl(url) {{
        if (!url) return url;
        var str = String(url);
        if (str.startsWith("data:") || str.startsWith("blob:") || str.includes("streamfree_proxy")) {{
            return url;
        }}
        if (str.startsWith("/")) {{
            return PROXY_ENDPOINT + encodeURIComponent(BASE_DOMAIN + str);
        }}
        if (str.startsWith("http://") || str.startsWith("https://")) {{
            return PROXY_ENDPOINT + encodeURIComponent(str);
        }}
        return url;
    }}

    var origFetch = window.fetch;
    window.fetch = function(input, init) {{
        if (typeof input === "string") {{
            input = rewriteUrl(input);
        }} else if (input && input.url) {{
            try {{
                input = new Request(rewriteUrl(input.url), init);
            }} catch(e) {{}}
        }}
        return origFetch.call(this, input, init);
    }};

    var origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {{
        var args = Array.prototype.slice.call(arguments, 2);
        url = rewriteUrl(url);
        return origOpen.apply(this, [method, url].concat(args));
    }};
}})();
</script>
"""
                if "<head>" in html:
                    html = html.replace("<head>", f"<head>{patch_script}", 1)
                elif "<head " in html:
                    html = re.sub(r'<head\b[^>]*>', r'\g<0>' + patch_script, html, count=1)
                else:
                    html = patch_script + html
                
                return HTMLResponse(content=html)
    except Exception as e:
        logger.warning(f"Failed fetching iframe content server-side for {iframe_src}: {e}")

    fallback_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="referrer" content="no-referrer">
    <title>HHPanda Player</title>
    <style>
        html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #000; overflow: hidden; display: flex; justify-content: center; align-items: center; }}
        iframe {{ width: 100%; height: 100%; border: none; }}
    </style>
</head>
<body>
    <iframe src="{iframe_src}" referrerpolicy="no-referrer" allowfullscreen="true" allow="autoplay; fullscreen; encrypted-media"></iframe>
</body>
</html>"""
    return HTMLResponse(content=fallback_html)

if __name__ == "__main__":
    import os
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="HHPanda Stremio Addon")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(hhpanda_router, prefix="/hhpanda")
    app.include_router(hhpanda_router)
    
    port = int(os.getenv("PORT", 7071))
    print(f"🚀 Starting HHPanda Stremio Addon on http://127.0.0.1:{port}/hhpanda/manifest.json")
    uvicorn.run(app, host="0.0.0.0", port=port)

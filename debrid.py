import httpx
import logging
import asyncio
from config import Config

logger = logging.getLogger("debrid")

class DebridProvider:
    async def check_availability(self, hashes: list) -> dict:
        """
        Given a list of torrent hashes, checks which ones are instantly cached.
        Returns a dict mapping hash -> bool.
        """
        raise NotImplementedError()

    async def get_stream_url(self, magnet_link: str, filename: str = None) -> str:
        """
        Adds torrent, resolves files, and returns the direct CDN download/stream URL.
        """
        raise NotImplementedError()

class RealDebridProvider(DebridProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.base_url = "https://api.real-debrid.com/rest/1.0"

    async def check_availability(self, hashes: list) -> dict:
        if not hashes:
            return {}
            
        results = {}
        # RD expects lowercase hashes
        hashes_lower = [h.lower() for h in hashes]
        
        # Batch hashes in chunks of 40 to avoid URL length issues
        chunk_size = 40
        async with httpx.AsyncClient(headers=self.headers, timeout=8.0) as client:
            for i in range(0, len(hashes_lower), chunk_size):
                chunk = hashes_lower[i:i+chunk_size]
                hash_list_str = "/".join(chunk)
                url = f"{self.base_url}/torrents/instantAvailability/{hash_list_str}"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        for h in chunk:
                            h_data = data.get(h, {})
                            # If 'rd' has entries, it's cached
                            results[h] = bool(h_data.get("rd"))
                    else:
                        logger.error(f"RD instantAvailability check returned {resp.status_code}: {resp.text}")
                except Exception as e:
                    logger.error(f"RD instantAvailability check failed: {e}")
                    
        # Populate any missing hashes as False
        for h in hashes_lower:
            if h not in results:
                results[h] = False
                
        return results

    async def get_stream_url(self, magnet_link: str, filename: str = None) -> str:
        async with httpx.AsyncClient(headers=self.headers, timeout=12.0) as client:
            # 1. Add Magnet
            resp = await client.post(f"{self.base_url}/torrents/addMagnet", data={"magnet": magnet_link})
            if resp.status_code not in (200, 201):
                logger.error(f"RD addMagnet failed: {resp.text}")
                return None
            data = resp.json()
            torrent_id = data.get("id")
            if not torrent_id:
                logger.error("RD returned no torrent_id")
                return None
            
            # 2. Get info
            info_resp = await client.get(f"{self.base_url}/torrents/info/{torrent_id}")
            if info_resp.status_code != 200:
                logger.error(f"RD info failed: {info_resp.text}")
                return None
            info = info_resp.json()
            
            # 3. Select Files (if waiting)
            if info.get("status") == "waiting_files_selection":
                files = info.get("files", [])
                video_files = [f for f in files if f.get("path", "").lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts'))]
                if video_files:
                    # Select largest video file
                    video_files.sort(key=lambda x: x.get("bytes", 0), reverse=True)
                    selected_id = video_files[0].get("id")
                    await client.post(f"{self.base_url}/torrents/selectFiles/{torrent_id}", data={"files": str(selected_id)})
                else:
                    await client.post(f"{self.base_url}/torrents/selectFiles/{torrent_id}", data={"files": "all"})
            
            # 4. Poll for completion
            for _ in range(7):
                info_resp = await client.get(f"{self.base_url}/torrents/info/{torrent_id}")
                if info_resp.status_code == 200:
                    info = info_resp.json()
                    status = info.get("status")
                    if status == "downloaded":
                        break
                    elif status in ("error", "dead", "magnet_error"):
                        logger.error(f"RD torrent entered error status: {status}")
                        return None
                await asyncio.sleep(1.5)
                
            if info.get("status") != "downloaded":
                logger.warning(f"RD torrent still downloading/processing: {info.get('status')}")
                return None
                
            links = info.get("links", [])
            if not links:
                logger.error("RD torrent finished but has no links")
                return None
                
            # 5. Unrestrict link
            rd_link = links[0]
            unrestrict_resp = await client.post(f"{self.base_url}/unrestrict/link", data={"link": rd_link})
            if unrestrict_resp.status_code != 200:
                logger.error(f"RD unrestrict failed: {unrestrict_resp.text}")
                return None
                
            unrestricted = unrestrict_resp.json()
            return unrestricted.get("download")

class TorBoxProvider(DebridProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.base_url = "https://api.torbox.app/v1/api"

    async def check_availability(self, hashes: list) -> dict:
        if not hashes:
            return {}
            
        results = {}
        hashes_lower = [h.lower() for h in hashes]
        
        chunk_size = 50
        async with httpx.AsyncClient(headers=self.headers, timeout=8.0) as client:
            for i in range(0, len(hashes_lower), chunk_size):
                chunk = hashes_lower[i:i+chunk_size]
                hashes_str = ",".join(chunk)
                url = f"{self.base_url}/torrents/checkcached?hash={hashes_str}"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        if isinstance(data, dict):
                            for h, val in data.items():
                                results[h.lower()] = val is not None
                        elif isinstance(data, list):
                            for item in data:
                                h = item.get("hash") or item.get("hash_string")
                                if h:
                                    results[h.lower()] = True
                    else:
                        logger.error(f"TorBox checkcached returned {resp.status_code}: {resp.text}")
                except Exception as e:
                    logger.error(f"TorBox checkcached check failed: {e}")
                    
        # Populate missing
        for h in hashes_lower:
            if h not in results:
                results[h] = False
                
        return results

    async def get_stream_url(self, magnet_link: str, filename: str = None) -> str:
        async with httpx.AsyncClient(headers=self.headers, timeout=12.0) as client:
            # 1. Add Magnet
            resp = await client.post(f"{self.base_url}/torrents/createtorrent", data={"magnet": magnet_link})
            if resp.status_code not in (200, 201):
                logger.error(f"TorBox createtorrent failed: {resp.text}")
                return None
            data = resp.json()
            inner_data = data.get("data", {})
            torrent_id = inner_data.get("torrent_id")
            if not torrent_id:
                logger.error(f"TorBox returned no torrent_id: {data}")
                return None
                
            # 2. Poll for file structure and download presence
            torrent_info = None
            for _ in range(7):
                list_resp = await client.get(f"{self.base_url}/torrents/mylist")
                if list_resp.status_code == 200:
                    torrents_list = list_resp.json().get("data", [])
                    for t in torrents_list:
                        # Match by ID or torrent_id
                        if t.get("id") == torrent_id or t.get("torrent_id") == torrent_id:
                            torrent_info = t
                            break
                if torrent_info and torrent_info.get("download_finished"):
                    break
                await asyncio.sleep(1.5)
                
            if not torrent_info:
                logger.error(f"TorBox failed to locate torrent: {torrent_id}")
                return None
                
            # 3. Find Best File ID
            files = torrent_info.get("files", [])
            file_id = None
            if files:
                video_files = [f for f in files if f.get("name", "").lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts'))]
                if video_files:
                    video_files.sort(key=lambda x: x.get("size", 0), reverse=True)
                    file_id = video_files[0].get("id")
                else:
                    file_id = files[0].get("id")
                    
            # 4. Request Download Link
            params = {
                "token": self.api_key,
                "torrent_id": torrent_id,
                "redirect": "false"
            }
            if file_id is not None:
                params["file_id"] = file_id
                
            dl_resp = await client.get(f"{self.base_url}/torrents/requestdl", params=params)
            if dl_resp.status_code != 200:
                logger.error(f"TorBox requestdl failed: {dl_resp.text}")
                return None
                
            dl_data = dl_resp.json()
            return dl_data.get("data")

class QBittorrentProvider(DebridProvider):
    def __init__(self):
        self.url = Config.QBITTORRENT_URL.rstrip("/")
        self.username = Config.QBITTORRENT_USER
        self.password = Config.QBITTORRENT_PASS
        self.client = httpx.AsyncClient(timeout=10.0)
        self.cookies = {}

    async def login(self) -> bool:
        try:
            resp = await self.client.post(
                f"{self.url}/api/v2/auth/login",
                data={"username": self.username, "password": self.password}
            )
            if resp.status_code == 200 and "Ok" in resp.text:
                self.cookies = resp.cookies
                return True
            logger.error(f"qBittorrent login failed: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"qBittorrent connection failed: {e}")
            return False

    async def check_availability(self, hashes: list) -> dict:
        if not hashes:
            return {}
            
        results = {h.lower(): False for h in hashes}
        if not self.cookies:
            await self.login()
            
        try:
            hashes_str = "|".join(hashes)
            resp = await self.client.get(
                f"{self.url}/api/v2/torrents/info",
                params={"hashes": hashes_str},
                cookies=self.cookies
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                    h = item.get("hash")
                    if h:
                        # Consider cached if fully completed (progress is 1.0)
                        results[h.lower()] = item.get("progress", 0) >= 1.0
            elif resp.status_code in (401, 403):
                if await self.login():
                    return await self.check_availability(hashes)
        except Exception as e:
            logger.error(f"qBittorrent check_availability failed: {e}")
            
        return results

    async def get_stream_url(self, magnet_link: str, filename: str = None) -> str:
        if not self.cookies:
            await self.login()
            
        import re
        m = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet_link)
        info_hash = m.group(1).lower() if m else ""
        if not info_hash:
            logger.error("Could not parse info_hash from magnet link")
            return None

        try:
            data = {
                "urls": magnet_link,
                "sequentialDownload": "true",
                "firstLastPiecePrio": "true"
            }
            resp = await self.client.post(
                f"{self.url}/api/v2/torrents/add",
                data=data,
                cookies=self.cookies
            )
            
            if resp.status_code in (401, 403):
                if await self.login():
                    resp = await self.client.post(
                        f"{self.url}/api/v2/torrents/add",
                        data=data,
                        cookies=self.cookies
                    )
                    
            if resp.status_code != 200:
                logger.error(f"qBittorrent failed to add torrent: {resp.text}")
                return None
                
            return f"qbittorrent://{info_hash}"
        except Exception as e:
            logger.error(f"qBittorrent get_stream_url error: {e}")
            return None

def get_debrid_provider() -> DebridProvider:
    if Config.REAL_DEBRID_API_KEY:
        return RealDebridProvider(Config.REAL_DEBRID_API_KEY)
    elif Config.TORBOX_API_KEY:
        return TorBoxProvider(Config.TORBOX_API_KEY)
    elif Config.QBITTORRENT_URL:
        return QBittorrentProvider()
    return None

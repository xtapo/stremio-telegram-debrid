import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import httpx
import re
from bs4 import BeautifulSoup
import urllib.parse
from moviesdrive_router import HEADERS, resolve_direct_stream_links

async def extract_series_archive_episodes(post_url: str, episode_num: int = 1):
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(post_url, headers=HEADERS)
        soup = BeautifulSoup(resp.text, 'html.parser')
        content = soup.find('div', class_='entry-content') or soup.find('article') or soup
        
        archive_links = []
        for a in content.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if 'archive/' in href or 'mdrive.' in href:
                archive_links.append({'text': text, 'url': href})
            elif 'hubcloud' in href:
                archive_links.append({'text': text, 'url': href})
                
        print(f"Found {len(archive_links)} buttons/archives on post:")
        for al in archive_links:
            print(f" - [{al['text']}] => {al['url']}")
            
        episode_hubcloud_links = []
        for al in archive_links:
            if 'archive/' in al['url'] or 'mdrive.' in al['url']:
                # Fetch archive page
                arc_resp = await client.get(al['url'], headers=HEADERS)
                arc_soup = BeautifulSoup(arc_resp.text, 'html.parser')
                # Hubcloud links in order correspond to episodes (Ep 1, Ep 2, Ep 3...)
                hc_in_arc = []
                for a in arc_soup.find_all('a', href=True):
                    if 'hubcloud' in a['href']:
                        hc_in_arc.append(a['href'])
                print(f"Archive [{al['text']}] has {len(hc_in_arc)} Hubcloud episode links")
                if len(hc_in_arc) >= episode_num:
                    target_ep_link = hc_in_arc[episode_num - 1]
                    episode_hubcloud_links.append({'quality': al['text'], 'url': target_ep_link})

        print(f"\nResolved Episode {episode_num} HubCloud links across qualities: {len(episode_hubcloud_links)}")
        for e in episode_hubcloud_links:
            print(f" -> Quality: {e['quality']} | Hubcloud: {e['url']}")
            # Resolve stream
            streams = await resolve_direct_stream_links(e['url'])
            print(f"    Direct Streams: {streams}")

if __name__ == '__main__':
    asyncio.run(extract_series_archive_episodes("https://new2.moviesdrive.christmas/spooky-in-love-season-1-2026/", episode_num=1))

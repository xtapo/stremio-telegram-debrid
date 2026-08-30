import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

async def test_gamerxyt():
    archive_url = "https://mdrive.lol/archive/6762/"
    post_url = "https://new3.moviesdrive.christmas/reacher-season-1-4/"
    
    # Level 2: archive page -> hubcloud link
    hc_url = await resolver.resolve_archive_page_episodes(archive_url, post_url, episode_num=1)
    print("Hubcloud episode 1 URL:", hc_url)
    
    # Level 3: Hubcloud page HTML
    first_html, _ = await resolver.fetch_text(hc_url, headers={"User-Agent": perf.USER_AGENT}, referer=resolver.HUBCLOUD_BASE + "/")
    print("Hubcloud HTML length:", len(first_html) if first_html else 0)
    
    soup1 = resolver.make_soup(first_html)
    for a in soup1.find_all("a", href=True):
        print(f"HubCloud Link: {a.get_text(strip=True)} -> {a['href']}")
        
    gamer_link = None
    for a in soup1.find_all("a", href=True):
        if any(host in a["href"] for host in resolver.GAMERXYT_HOSTS):
            gamer_link = a["href"]
            break
            
    print("GamerXYT link:", gamer_link)
    
    # Level 4: GamerXYT HTML
    second_html, _ = await resolver.fetch_text(gamer_link, headers={"User-Agent": perf.USER_AGENT}, referer=hc_url)
    with open("scratch/reacher_gamerxyt.html", "w", encoding="utf-8") as f:
        f.write(second_html or "")
    print("Saved reacher_gamerxyt.html, length:", len(second_html) if second_html else 0)
    
    soup2 = resolver.make_soup(second_html)
    for a in soup2.find_all("a", href=True):
        print(f"GamerXYT Link: {a.get_text(strip=True)} -> {a['href']}")
        
    # Check all collected streams:
    all_streams = resolver._collect_stream_links(second_html)
    print("\nAll collected streams from GamerXYT:")
    for s in all_streams:
        print("Stream:", s)

    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(test_gamerxyt())

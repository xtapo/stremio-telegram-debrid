import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vidking_router import vidking_stream_handler

async def test():
    res = await vidking_stream_handler('movie', 'tt0137523')
    streams = res.get('streams', [])
    print(f"Total streams for Fight Club: {len(streams)}")
    for s in streams:
        name = s.get('name', '').replace('\n', ' ').encode('ascii', 'replace').decode()
        ext = s.get('externalUrl')
        url = s.get('url')
        target = ext if ext else (url[:70] + "...")
        print(f"  * [{name}] -> {target}")

if __name__ == '__main__':
    asyncio.run(test())

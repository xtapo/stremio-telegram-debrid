import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from movies2watch_router import movies2watch_stream_handler

class DummyRequest:
    base_url = 'http://localhost:7860'

async def main():
    req = DummyRequest()
    res = await movies2watch_stream_handler(req, 'movie', 'movies2watch:movie:deadpool-wolverine-65261')
    streams = res.get('streams', [])
    print(f'Generated {len(streams)} streams for Deadpool & Wolverine:')
    for idx, s in enumerate(streams[:10]):
        name_clean = s.get('name', '').encode('ascii', 'ignore').decode('ascii').replace('\n', ' | ')
        target = s.get('url') or s.get('externalUrl') or ''
        print(f' {idx+1}. {name_clean} -> {target[:60]}')

if __name__ == '__main__':
    asyncio.run(main())

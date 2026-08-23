import sys
sys.path.insert(0, ".")
import asyncio
import fourkhdhub_catalog as catalog

async def debug_slug():
    meta = await catalog.get_meta_for_slug("backrooms-movie-7787", item_type="movie")
    print("get_meta_for_slug:", meta)
    resolved = await catalog.find_imdb_for_fourkhdhub_slug("backrooms-movie-7787", media_type="movie")
    print("find_imdb_for_fourkhdhub_slug:", resolved)
    if resolved:
        subs = await catalog.fetch_opensubtitles(resolved, media_type="movie", extra="filename=backrooms.movie.7787.mkv")
        print("fetch_opensubtitles count:", len(subs))

asyncio.run(debug_slug())

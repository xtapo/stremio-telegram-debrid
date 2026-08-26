import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_perf as perf

async def test():
    print("Testing fetch_portal_mirrors()...")
    mirrors = await perf.fetch_portal_mirrors()
    print("Portal mirrors found:", mirrors)
    assert len(mirrors) > 0, "No mirrors found from portal!"
    
    print("\nTesting discover_active_base(force=True)...")
    active = await perf.discover_active_base(force=True)
    print("Active base discovered and pinned:", active)
    assert active is not None, "Failed to discover active base!"
    print("Active base candidate bases:", perf.candidate_bases())
    
    await perf.aclose_client()
    print("\nALL PORTAL DISCOVERY TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test())

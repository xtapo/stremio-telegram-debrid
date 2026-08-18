import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from fastapi.testclient import TestClient

from addon import app
from config import Config

def test_subtitle_toggle():
    client = TestClient(app)

    # 1. Set ENABLE_SUBTITLES=True, AUTO_VIET_SUB=False
    print("1. Testing with ENABLE_SUBTITLES=True and AUTO_VIET_SUB=False (User disabled translation)...")
    res_update = client.post("/api/config/update", json={"enable_subtitles": True, "auto_vietsub": False})
    assert res_update.status_code == 200
    assert res_update.json()["services"]["enable_subtitles"] is True
    assert res_update.json()["services"]["auto_vietsub"] is False

    # Check MoviesDrive subtitles when AUTO_VIET_SUB is False:
    # vi_fast and vi_quality should NOT be present in subtitles!
    res_md_subs = client.get("/moviesdrive/subtitles/movie/moviesdrive:kanguva-2024.json")
    assert res_md_subs.status_code == 200
    md_subs = res_md_subs.json().get("subtitles", [])
    vi_ai_tracks = [s for s in md_subs if "vi_fast" in s.get("id", "") or "vi_quality" in s.get("id", "")]
    assert len(vi_ai_tracks) == 0, f"Expected 0 AI translation tracks when auto_vietsub is False, got: {vi_ai_tracks}"
    print(f"MoviesDrive returned {len(md_subs)} subs (AI VietSub tracks correctly disabled: {len(vi_ai_tracks)}).")

    # Check Vidking subtitles when AUTO_VIET_SUB is False:
    res_vk_subs = client.get("/vidking/subtitles/movie/vidking:movie:550.json")
    assert res_vk_subs.status_code == 200
    vk_subs = res_vk_subs.json().get("subtitles", [])
    vk_ai_tracks = [s for s in vk_subs if "vi_fast" in s.get("id", "") or "vi_quality" in s.get("id", "")]
    assert len(vk_ai_tracks) == 0
    print(f"Vidking returned {len(vk_subs)} subs (AI VietSub tracks correctly disabled: {len(vk_ai_tracks)}).")

    # Check HDHub4u subtitles when AUTO_VIET_SUB is False:
    res_hd_subs = client.get("/hdhub4u/subtitles/movie/hdhub4u:123.json")
    assert res_hd_subs.status_code == 200
    hd_subs = res_hd_subs.json().get("subtitles", [])
    assert len(hd_subs) == 0
    print(f"HDHub4u returned {len(hd_subs)} subs (AI VietSub tracks correctly disabled).")

    # 2. Turn AUTO_VIET_SUB=True
    print("\n2. Testing with ENABLE_SUBTITLES=True and AUTO_VIET_SUB=True (Translation enabled)...")
    res_update_sub = client.post("/api/config/update", json={"enable_subtitles": True, "auto_vietsub": True})
    assert res_update_sub.status_code == 200
    res_md_subs_on = client.get("/moviesdrive/subtitles/movie/moviesdrive:kanguva-2024.json")
    md_subs_on = res_md_subs_on.json().get("subtitles", [])
    vi_ai_on = [s for s in md_subs_on if "vi_fast" in s.get("id", "") or "vi_quality" in s.get("id", "")]
    assert len(vi_ai_on) == 2, f"Expected 2 AI translation tracks, got: {vi_ai_on}"
    print(f"MoviesDrive returned {len(md_subs_on)} subs (AI VietSub tracks correctly enabled: {len(vi_ai_on)}).")

    # 3. Master switch ENABLE_SUBTITLES=False
    print("\n3. Testing master switch ENABLE_SUBTITLES=False (All subtitles completely disabled)...")
    res_update_off = client.post("/api/config/update", json={"enable_subtitles": False})
    assert res_update_off.status_code == 200
    assert res_update_off.json()["services"]["enable_subtitles"] is False

    # Check manifests
    main_man = client.get("/manifest.json").json()
    assert "subtitles" not in main_man.get("resources", [])
    vk_man = client.get("/vidking/manifest.json").json()
    vk_res = [r if isinstance(r, str) else r.get("name") for r in vk_man.get("resources", [])]
    assert "subtitles" not in vk_res

    # Check endpoint returns empty list
    res_sub_empty = client.get("/subtitles/movie/tt0137523.json")
    assert res_sub_empty.json() == {"subtitles": []}

    print("\n[OK] ALL SUBTITLE & TRANSLATION TOGGLE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_subtitle_toggle()

import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('scratch/film4k_channels.json', 'r', encoding='utf-8') as f:
    channels = json.load(f).get('channels', [])

def categorize_channel(ch):
    name = ch.get('name', '').lower()
    ch_id = ch.get('id', '').lower()
    
    if any(k in name or k in ch_id for k in ['vtv']):
        return 'VTV'
    if any(k in name or k in ch_id for k in ['htv', 'htvc']):
        return 'HTV'
    if any(k in name or k in ch_id for k in ['k+', 'k-plus', 'k plus']):
        return 'K+ Truyền Hình'
    if any(k in name or k in ch_id for k in ['vtc']):
        return 'VTC'
    if any(k in name or k in ch_id for k in ['sport', 'thể thao', 'football', 'golf', 'tennis', 'nba', 'uefa', 'fifa', 'fpt sport', 'on sport']):
        return 'Thể Thao'
    if any(k in name or k in ch_id for k in ['hbo', 'cinemax', 'cinema', 'phim', 'movie', 'hollywood', 'action', 'box', 'warner', 'axn']):
        return 'Phim Truyện & Điện Ảnh'
    if any(k in name or k in ch_id for k in ['cartoon', 'disney', 'anime', 'kid', 'thiếu nhi', 'hoạt hình', 'bibi', 'dreamworks']):
        return 'Thiếu Nhi & Hoạt Hình'
    if any(k in name or k in ch_id for k in ['discovery', 'nat geo', 'national geographic', 'animal', 'khám phá', 'history', 'travel', 'planet', 'tlc', 'food']):
        return 'Khoa Học & Khám Phá'
    if any(k in name or k in ch_id for k in ['cnn', 'bbc', 'news', 'tin tức', 'thời sự', 'bloomberg', 'nhk', 'dw', 'france 24']):
        return 'Tin Tức & Thời Sự'
    if any(k in name or k in ch_id for k in ['music', 'âm nhạc', 'mnet', 'mtv', 'itv', 'ca nhạc']):
        return 'Âm Nhạc & Giải Trí'
    if any(k in name or k in ch_id for k in ['hà nội', 'hanoitv', 'thvl', 'vĩnh long', 'đà nẵng', 'hải phòng', 'cần thơ', 'bình dương', 'đồng nai', 'quảng ninh', 'huế', 'ninh bình', 'bình định', 'thái nguyên', 'khánh hòa', 'tây ninh', 'long an', 'tiền giang', 'bến tre', 'an giang', 'kiên giang', 'cà mau', 'bạc liêu', 'sóc trăng', 'trà vinh', 'hậu giang', 'vũng tàu', 'lâm đồng', 'đắk lắk', 'gia lai', 'kon tum', 'đắk nông', 'bình phước', 'bình thuận', 'ninh thuận', 'phú yên', 'quảng ngãi', 'quảng nam', 'quảng trị', 'quảng bình', 'hà tĩnh', 'nghệ an', 'thanh hóa', 'nam định', 'thái bình', 'hải dương', 'hưng yên', 'bắc ninh', 'bắc giang', 'vĩnh phúc', 'phú thọ', 'hà giang', 'tuyên quang', 'cao bằng', 'bắc kạn', 'lạng sơn', 'lào cai', 'yên bái', 'điện biên', 'lai châu', 'sơn la', 'hòa bình']):
        return 'Đài Địa Phương'
    return 'Kênh Tổng Hợp & Quốc Tế'

categories = {}
for ch in channels:
    cat = categorize_channel(ch)
    categories.setdefault(cat, []).append(ch)

for cat, ch_list in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"[{cat}]: {len(ch_list)} kênh")
    print("   Sample:", [c['name'] for c in ch_list[:4]])

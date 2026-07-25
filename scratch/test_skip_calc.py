import math

def calculate_pages_to_fetch(skip: int, limit: int = 30, api_page_size: int = 30):
    start_item = skip
    end_item = skip + limit
    
    start_page = (start_item // api_page_size) + 1
    end_page = ((end_item - 1) // api_page_size) + 1
    
    offset_in_concatenated = start_item % api_page_size
    
    return start_page, end_page, offset_in_concatenated

test_skips = [0, 20, 30, 40, 60, 100, 120, 200]
for s in test_skips:
    sp, ep, off = calculate_pages_to_fetch(s)
    print(f"skip={s:3d} -> Fetch API pages {sp} to {ep}, slice offset={off}")

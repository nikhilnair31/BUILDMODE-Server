from datetime import date
from core.content.parser import parse_query

examples = [
    '"red dress" AND (shoes OR sandals) last week #ff00ff since 2021-01-01',
    "cats OR dogs NOT 'angora' before 2020",
    "photos from jan 2024 to mar 2024 blue green #0f0",
    "site:example.com \"meeting notes\" AND budget last 3 months",
    "sunset #f4a460 between 2019 and 2021",
    "recent images of coral red OR maroon since May 2020",
    "vibe: blue aesthetic like warm-tones",
    "beach",
    "inbox@company.com meeting notes",
    "FF00AABB",  # hex without #
]
for ex in examples:
    print(f"QUERY: {ex}")
    out = parse_query(ex)
    print(f"OUT: {out}")
    print("-"*60)
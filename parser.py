import re
import dateparser
from datetime import datetime, timedelta

def parse_time_input(text):
    parsed = dateparser.parse(text, settings={
        'PREFER_DATES_FROM': 'past',
        'RELATIVE_BASE': datetime.now()
    })

    return parsed  # may return None if parsing fails

def is_color_code(text):
    return bool(re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", text)) or \
           bool(re.match(r"rgb\((\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})\)", text))

def rgb_to_vec(rgb_str):
    # Expecting 'rgb(255, 0, 0)'
    match = re.match(r"rgb\((\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})\)", rgb_str)
    if match:
        r, g, b = map(int, match.groups())
        # Normalize to vector or pass to embedding service
        return f"[{r/255:.3f}, {g/255:.3f}, {b/255:.3f}]"
    return None
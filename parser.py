import re
import dateparser
from datetime import datetime, timedelta

def parse_time_input(text):
    text = text.lower().strip()
    now = datetime.now()
    
    if "yesterday" in text:
        return now - timedelta(days=1)
    elif "day" in text:
        match = re.search(r"(\d+)\s*days?", text)
        if match:
            return now - timedelta(days=int(match.group(1)))
    elif "week" in text:
        return now - timedelta(weeks=1)
    elif "month" in text:
        return now - timedelta(days=30)
    return None

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
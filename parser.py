import re
import dateparser
from datetime import datetime

DATE_HINT_REGEX = re.compile(
    r"(yesterday|today|ago|last|next|week|month|year|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+|\d{4})",
    flags=re.IGNORECASE
)

def parse_time_input(text):
    if not DATE_HINT_REGEX.search(text):
        return None  # Fast exit: no date-like terms found

    parsed = dateparser.parse(text, settings={
        'PREFER_DATES_FROM': 'past',
        'RELATIVE_BASE': datetime.now()
    })
    return parsed

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

def extract_color_code(text):
    hex_match = re.search(r"#(?:[0-9a-fA-F]{3}){1,2}", text)
    if hex_match:
        return hex_match.group(0)
    rgb_match = re.search(r"\[\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\]", text)
    if rgb_match:
        return [int(rgb_match.group(i)) for i in range(1, 4)]
    return None

def clean_text_of_color_and_time(text):
    text = re.sub(r"#(?:[0-9a-fA-F]{3}){1,2}", "", text)  # remove hex
    text = re.sub(r"\[\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\]", "", text)  # remove RGB
    text = re.sub(r"(yesterday|last week|a month ago|today|[0-9]+ days? ago|[A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?(?:, \d{4})?)", "", text, flags=re.IGNORECASE)  # simple NLP
    return text.strip()
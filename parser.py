# parser.py

import re
import pytz
import logging
import parsedatetime
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATE_HINT_REGEX = re.compile(
    r"(yesterday|today|ago|last|next|week|month|year|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+|\d{4})",
    flags=re.IGNORECASE
)

cal = parsedatetime.Calendar()

def timezone_to_start_of_day_ts(tz_name):
    try:
        user_tz = pytz.timezone(tz_name)
    except Exception as e:
        logger.warning(f"Invalid timezone received: {tz_name}. Defaulting to UTC.")
        user_tz = pytz.UTC

    # Current time in user's timezone
    now_local = datetime.now(user_tz)
    logger.info(f"User's local time: {now_local}")

    # Start of day in local time, then converted to UTC
    start_of_day_local = user_tz.localize(datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0))
    start_of_day_utc = start_of_day_local.astimezone(pytz.UTC)
    start_of_day_ts = int(start_of_day_utc.timestamp())

    return start_of_day_ts

def parse_time_input(text):
    if not DATE_HINT_REGEX.search(text):
        return None  # Short-circuit for non-date-like queries

    time_struct, parse_status = cal.parse(text)
    if parse_status == 0:
        return None  # Couldn’t parse into a date

    converted_time = datetime(*time_struct[:6])  # Convert to datetime
    # logger.info(f"Parsed time: {converted_time}")

    return converted_time

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
# parser.py

import re
import pytz
import logging
import parsedatetime
from timefhuman import timefhuman, tfhConfig
from datetime import date, datetime, timedelta
from dateutil import parser as dateutil_parser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = tfhConfig(return_matched_text=True)

def timezone_to_start_of_day_ts(tz_name):
    try:
        user_tz = pytz.timezone(tz_name)

        now_local = datetime.now(user_tz)

        start_of_day_local = user_tz.localize(datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0))
        start_of_day_utc = start_of_day_local.astimezone(pytz.UTC)
        start_of_day_ts = int(start_of_day_utc.timestamp())

        return start_of_day_ts
    except Exception as e:
        logger.warning(f"Invalid timezone received: {tz_name}. Defaulting to UTC.")
        return int(datetime.now(pytz.UTC).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

def sanitize_tsquery(user_input: str) -> str:
    """
    Convert user input into a safe PostgreSQL to_tsquery string.
    Supports AND/OR/NOT operators and minimal parentheses.
    """
    if not user_input:
        return ""

    q = user_input.strip().lower()

    # Replace word operators with symbols
    q = re.sub(r"\band\b", "&", q)
    q = re.sub(r"\bor\b", "|", q)
    q = re.sub(r"\bnot\b", "!", q)

    # Keep words, operators, and parens; drop other punctuation
    q = re.sub(r"[^a-z0-9_\s\&\|\!\(\)]", " ", q)

    # Tokenize into words, operators, and parens
    tokens = re.findall(r"\(|\)|\&|\||\!|[a-z0-9_]+", q)

    out = []
    prev_was_term_or_close = False  # True if previous token is word or ')'
    prev_token = None

    def push_and_if_needed():
        if prev_was_term_or_close:
            out.append("&")

    for tok in tokens:
        if tok in {"&", "|"}:
            # Avoid consecutive operators or leading operator
            if prev_token in {None, "&", "|", "!", "("}:
                continue
            out.append(tok)
            prev_was_term_or_close = False

        elif tok == "!":
            # If a NOT follows a term/close, insert implicit AND
            push_and_if_needed()
            out.append("!")
            prev_was_term_or_close = False  # next must be a term or '('

        elif tok == "(":
            # Implicit AND before '(' if previous was a term/close
            push_and_if_needed()
            out.append("(")
            prev_was_term_or_close = False

        elif tok == ")":
            # Only close if last output was a term or ')'
            if prev_was_term_or_close:
                out.append(")")
            # keep prev_was_term_or_close = True (still a "closed" term)

        else:
            # word/lexeme
            if prev_token == "!":
                # ok: ! word
                pass
            else:
                # Implicit AND between adjacent words / after ')'
                push_and_if_needed()
            out.append(tok)  # optionally add ':*' for prefix: f"{tok}:*"
            prev_was_term_or_close = True

        prev_token = tok if tok != ")" else ")"

    # Drop trailing operator/NOT/implicit open
    while out and out[-1] in {"&", "|", "!", "("}:
        out.pop()

    return " ".join(out)
def extract_time_filter(query_text: str):
    """
    Extract natural language time expressions from query_text.
    Returns (cleaned_query, (start, end)) or (cleaned_query, None).
    """
    matches = timefhuman(query_text, config=config)

    if not matches:
        return query_text, None

    # For now just use the first match
    matched_text, span, parsed_dt = matches[0]

    # Remove the matched substring using indices (safer than .replace)
    start_idx, end_idx = span
    cleaned_text = (query_text[:start_idx] + query_text[end_idx:]).strip()

    # Normalize into a (start, end) tuple
    if isinstance(parsed_dt, datetime):
        start = parsed_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = parsed_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        time_filter = (int(start.timestamp()), int(end.timestamp()))
    elif isinstance(parsed_dt, tuple) and all(isinstance(d, datetime) for d in parsed_dt):
        time_filter = tuple(int(d.timestamp()) for d in parsed_dt)
    else:
        time_filter = None  # skip weird outputs for now

    return cleaned_text, time_filter

# parser.py

import re, pytz, logging
from datetime import datetime
from timefhuman import timefhuman, tfhConfig
from core.content.images import hex_to_rgb
from core.utils.timing import timed_route

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = tfhConfig(return_matched_text=True)

CSS_COLOR_HEX = {
    # core CSS colors (subset; add more as needed)
    "black":"#000000","white":"#ffffff","red":"#ff0000","green":"#008000","blue":"#0000ff",
    "yellow":"#ffff00","cyan":"#00ffff","magenta":"#ff00ff","purple":"#800080","orange":"#ffa500",
    "pink":"#ffc0cb","brown":"#a52a2a","gray":"#808080","grey":"#808080","teal":"#008080",
    "navy":"#000080","maroon":"#800000","olive":"#808000","lime":"#00ff00","indigo":"#4b0082",
    "violet":"#ee82ee","gold":"#ffd700","silver":"#c0c0c0","beige":"#f5f5dc","coral":"#ff7f50",
    "salmon":"#fa8072","tan":"#d2b48c","turquoise":"#40e0d0","lavender":"#e6e6fa"
}
HEX_PATTERN = re.compile(r'#?[0-9a-fA-F]{6}\b')

@timed_route("timezone_to_start_of_day_ts")
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

@timed_route("sanitize_tsquery")
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

@timed_route("extract_time_filter")
def extract_time_filter(query_text: str, user_tz: str = "UTC"):
    if query_text is None or query_text == "":
        return query_text, None
    
    safe_text = re.sub(r'[^0-9a-zA-Z\s]', ' ', query_text)
    matches = timefhuman(safe_text, config=config)

    if not matches:
        return query_text, None

    # For now just use the first match
    matched_text, span, parsed_dt = matches[0]
    start_idx, end_idx = span
    cleaned_text = (query_text[:start_idx] + query_text[end_idx:]).strip()

    tz = pytz.timezone(user_tz)

    if isinstance(parsed_dt, datetime):
        # localize to user tz
        parsed_local = parsed_dt.astimezone(tz)
        start_local = parsed_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local   = parsed_local.replace(hour=23, minute=59, second=59, microsecond=999999)

        # convert to UTC epoch
        time_filter = (
            int(start_local.astimezone(pytz.UTC).timestamp()),
            int(end_local.astimezone(pytz.UTC).timestamp())
        )

    elif isinstance(parsed_dt, tuple) and all(isinstance(d, datetime) for d in parsed_dt):
        time_filter = tuple(
            int(d.astimezone(tz).astimezone(pytz.UTC).timestamp())
            for d in parsed_dt
        )

    else:
        time_filter = None

    return cleaned_text, time_filter

@timed_route("extract_time_filter")
def extract_color_filter(query_text: str):
    if not query_text:
        return query_text, None

    # --- check for hex code ---
    m = HEX_PATTERN.search(query_text)
    if m:
        rgb = hex_to_rgb(m.group(0))
        # keep as RGB if you don’t have Lab conversion yet
        return (query_text[:m.start()] + query_text[m.end():]).strip(), [*rgb]

    # --- check for color names ---
    tokens = re.findall(r'[a-zA-Z]+', query_text)
    for t in tokens:
        name = t.lower()
        if name in CSS_COLOR_HEX:
            rgb = hex_to_rgb(CSS_COLOR_HEX[name])
            cleaned = re.sub(r'\b' + re.escape(t) + r'\b', ' ', query_text, count=1).strip()
            return cleaned, [*rgb]

    return query_text, None
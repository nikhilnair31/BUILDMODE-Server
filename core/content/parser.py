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

DATE_HINT_REGEX = re.compile(
    r"(yesterday|today|ago|last|next|week|month|year|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+|\d{4})",
    flags=re.IGNORECASE
)

cal = parsedatetime.Calendar()

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

def parse_time_input(text, user_tz='UTC'):
    logger.info(f"Parsing time input: {text} with user timezone: {user_tz}")
    try:
        if not DATE_HINT_REGEX.search(text):
            return None
        
        user_timezone = pytz.timezone(user_tz)
        now_user_tz = datetime.now(user_timezone)
        time_struct, parse_status = cal.parse(text, now_user_tz.timetuple())
        if parse_status == 0:
            return None  # Couldn’t parse into a date
        # logger.info(f"Parsed time struct: {time_struct}, status: {parse_status}")

        local_dt = datetime(*time_struct[:6])
        # logger.info(f"local_dt: {local_dt.strftime('%d/%m/%Y %H:%M')}")

        localized_dt = user_timezone.localize(local_dt)
        # logger.info(f"localized_dt: {localized_dt.strftime('%d/%m/%Y %H:%M')}")
            
        normalized_local = localized_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        # logger.info(f"normalized_local: {normalized_local.strftime('%d/%m/%Y %H:%M')}")

        # Convert to UTC
        utc_dt = normalized_local.astimezone(pytz.utc)

        return utc_dt
    except Exception as e:
        logger.error(f"Error parsing time input: {e}")
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

# ---------------------------------------------------------------------------

# Small set of common CSS color names (expand as needed)
CSS_COLOR_NAMES = {
    "white","black","red","green","blue","yellow","pink","purple","orange","brown","gray","grey","cyan","magenta",
    "maroon","olive","lime","teal","navy","silver","gold","beige","indigo","violet","khaki","coral","salmon"
}
VIBE_KEYWORDS = {
    "vibe", "vibes", "vibey", "vibe-y", "mood", "like", "similar", "aesthetic", "style", "feel", "feels",
    "tone", "vibe-ish", "vibeish", "vibeslike", "vibes-like"
}
HEX_RE = re.compile(r'#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b')
HEX_NOHASH_RE = re.compile(r'\b([0-9a-fA-F]{6})\b')  # sometimes people type ffaabb without #
_TOKEN_RE = re.compile(r'\(|\)|\bAND\b|\bOR\b|\bNOT\b', flags=re.IGNORECASE)

config = tfhConfig(return_matched_text=True)

def extract_quoted_phrases(q):
    """
    Returns (quoted_phrases, remainder)
    quoted_phrases: list of strings found in "double quotes" or 'single quotes'
    remainder: input with quotes removed (quotes replaced by single spaces)
    """
    pattern = r'(?:"([^"]+)")|(?:\'([^\']+)\')'
    phrases = []
    def _rep(m):
        g1 = m.group(1) or m.group(2)
        phrases.append(g1)
        return " "  # replace with space to keep indexes reasonable
    remainder = re.sub(pattern, _rep, q)
    return phrases, remainder

def extract_colors(q):
    """
    Returns (colors, remainder)
    colors: list of dicts like {"type":"hex","value":"#aabbcc"} or {"type":"name","value":"red"}
    """
    found = []
    remainder = q
    # hex with hash
    for m in HEX_RE.finditer(q):
        found.append({"type":"hex","value":m.group(0)})
    remainder = HEX_RE.sub(" ", remainder)

    # color names (word boundaries)
    # we match longer names first by sorting by length
    for name in sorted(CSS_COLOR_NAMES, key=len, reverse=True):
        pattern = r'\b' + re.escape(name) + r'\b'
        # case-insensitive match
        if re.search(pattern, remainder, flags=re.IGNORECASE):
            # find all occurrences
            for m in re.finditer(pattern, remainder, flags=re.IGNORECASE):
                found.append({"type":"name","value":m.group(0).lower()})
            remainder = re.sub(pattern, " ", remainder, flags=re.IGNORECASE)

    # optional: hex without #
    # only accept if there are no digits near it (simple heuristic)
    for m in HEX_NOHASH_RE.finditer(remainder):
        val = m.group(1)
        # avoid false positives like timestamps with hex digits; we can require at least one letter
        if re.search(r'[a-fA-F]', val):
            found.append({"type":"hex","value":"#" + val})
            remainder = remainder.replace(val, " ")
    return found, remainder

def _parse_date_str(s):
    s = s.strip()
    if not s:
        return None
    try:
        dt = dateutil_parser.parse(s, default=datetime.now())
        return dt.date()
    except Exception:
        return None

def extract_time_range(q):
    """
    Attempts to find a time filter in natural language and return (time_range, remainder)
    time_range is either None or a dict: {"start": date or None, "end": date or None, "raw": matched_text}
    Supports patterns like:
      - "last week", "last 2 months", "2 years ago"
      - "since 2021", "after Jan 2020", "before 2019-12-31"
      - "between Jan 2020 and May 2021", "from 2020-01-01 to 2020-12-31"
    """
    today = date.today()

    remainder = q
    # canonical patterns
    patterns = [
        # between ... and ...
        (r'\bbetween\s+(.+?)\s+and\s+(.+?)(?:\b|$)', 'between_and'),
        (r'\bfrom\s+(.+?)\s+(?:to|-)\s+(.+?)(?:\b|$)', 'from_to'),
        # last N unit / last unit
        (r'\blast\s+(\d+)?\s*(day|week|month|year)s?\b', 'last_n'),
        (r'(\d+)\s*(day|week|month|year)s?\s+ago\b', 'n_ago'),
        (r'\bsince\s+(.+?)(?:\b|$)', 'since'),
        (r'\bafter\s+(.+?)(?:\b|$)', 'after'),
        (r'\bbefore\s+(.+?)(?:\b|$)', 'before'),
        # explicit single date like "on 2021-05-01" or "on May 2020"
        (r'\bon\s+(.+?)(?:\b|$)', 'on'),
    ]

    for pat, kind in patterns:
        m = re.search(pat, remainder, flags=re.IGNORECASE)
        if not m:
            continue
        raw = m.group(0)
        try:
            if kind in ('between_and', 'from_to'):
                a = m.group(1).strip()
                b = m.group(2).strip()
                da = _parse_date_str(a)
                db = _parse_date_str(b)
                # best-effort: if one is a year only, interpret as start/end of year
                if da and len(a) == 4 and re.match(r'^\d{4}$', a):
                    da = date(da.year, 1, 1)
                if db and len(b) == 4 and re.match(r'^\d{4}$', b):
                    db = date(db.year, 12, 31)
                tr = {"start": da, "end": db, "raw": raw}
            elif kind == 'last_n':
                n = m.group(1)
                unit = m.group(2).lower()
                n = int(n) if n else 1
                if unit.startswith('day'):
                    start = today - timedelta(days=n)
                    end = today
                elif unit.startswith('week'):
                    start = today - timedelta(weeks=n)
                    end = today
                elif unit.startswith('month'):
                    # approximate months as 30 days
                    start = today - timedelta(days=30 * n)
                    end = today
                else:  # year
                    start = date(today.year - n, today.month, today.day)
                    end = today
                tr = {"start": start, "end": end, "raw": raw}
            elif kind == 'n_ago':
                n = int(m.group(1))
                unit = m.group(2).lower()
                if unit.startswith('day'):
                    point = today - timedelta(days=n)
                elif unit.startswith('week'):
                    point = today - timedelta(weeks=n)
                elif unit.startswith('month'):
                    point = today - timedelta(days=30 * n)
                else:
                    point = date(today.year - n, today.month, today.day)
                tr = {"start": None, "end": point, "raw": raw}
            elif kind == 'since' or kind == 'after':
                s = m.group(1).strip()
                d = _parse_date_str(s)
                tr = {"start": d, "end": None, "raw": raw}
            elif kind == 'before':
                s = m.group(1).strip()
                d = _parse_date_str(s)
                tr = {"start": None, "end": d, "raw": raw}
            elif kind == 'on':
                s = m.group(1).strip()
                d = _parse_date_str(s)
                tr = {"start": d, "end": d, "raw": raw}
            else:
                tr = None
        except Exception:
            tr = None

        if tr:
            remainder = remainder.replace(raw, " ")
            return tr, remainder

    return None, remainder

def _is_ocr_like_token(tok):
    """
    Heuristics to detect OCR/exact tokens:
      - contains URL/email-like characters: @, :, /, . (short domain), backslash
      - long token length (>=20)
      - many digits (>=3)
      - long uppercase run (e.g. 'ABCDEF')
    """
    if not tok or not isinstance(tok, str):
        return False
    if re.search(r'[@:/\\]|\.com\b|site:', tok, flags=re.IGNORECASE):
        return True
    if len(tok) >= 20:
        return True
    digit_count = sum(1 for c in tok if c.isdigit())
    if digit_count >= 3:
        return True
    if re.search(r'[A-Z]{3,}', tok):
        return True
    # things like 'INV-12345' or long hex-like token: many non-alpha characters
    non_alpha = sum(1 for c in tok if not c.isalnum())
    if non_alpha >= 2:
        return True
    return False

def _contains_vibe_marker(q_lower):
    # quick check for vibe keywords or '-ish' adjectives or "like" used as comparator
    if any(k in q_lower for k in VIBE_KEYWORDS):
        return True
    if re.search(r'\b\w+-ish\b', q_lower):  # blue-ish, warm-ish
        return True
    # "like <noun>" often indicates an example-based / semantic search
    if re.search(r'\blike\s+\w+', q_lower):
        return True
    return False

def classify_intent(query, parsed=None):
    """
    Returns a dict: {'intent': 'exact'|'fuzzy'|'vibe', 'score':float, 'features': {...}}
    Heuristics (explainable):
      - exact: quoted phrases OR OCR-like tokens OR presence of explicit site:/url/email
      - vibe: presence of vibe keywords OR color names OR '-ish' or 'like' usage
      - fuzzy: short (<=3 tokens) + short avg token length and no vibe markers/quoted phrases
    """
    q = query or ""
    q_lower = q.lower()
    quoted = parsed.get("quoted_phrases") if parsed else []
    colors = parsed.get("colors") if parsed else []
    free_text = parsed.get("free_text") if parsed else q

    tokens = re.findall(r'\S+', free_text)
    token_count = len(tokens)
    avg_token_len = (sum(len(t) for t in tokens) / token_count) if token_count else 0

    # detect OCR-like tokens anywhere in the original query
    any_ocr = any(_is_ocr_like_token(tok) for tok in re.findall(r'\S+', q))

    # features for explanation
    features = {
        "has_quoted": bool(quoted),
        "has_colors": bool(colors),
        "has_vibe_marker": _contains_vibe_marker(q_lower),
        "any_ocr_like_token": any_ocr,
        "token_count": token_count,
        "avg_token_len": round(avg_token_len, 2)
    }

    # Primary heuristics
    if features["has_quoted"] or features["any_ocr_like_token"] or re.search(r'\bsite:|\.\w{2,4}\b|@', q_lower):
        intent = "exact"
        score = 0.95
    elif features["has_vibe_marker"] or features["has_colors"]:
        intent = "vibe"
        score = 0.85
    else:
        # short queries probably need fuzzy/typo tolerant matching
        if token_count <= 3 and avg_token_len <= 8:
            intent = "fuzzy"
            score = 0.75
        else:
            # longer free-text with no vibe markers — treat as vibe/semantic by default
            intent = "vibe"
            score = 0.6

    return {"intent": intent, "score": score, "features": features}

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

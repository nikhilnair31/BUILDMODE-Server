# digest.py

import os, ast, json, logging, re, requests, yaml
from linkpreview import link_preview
from collections import Counter, defaultdict
from datetime import datetime, time, UTC, timedelta, timezone
from pathlib import Path
from typing import List
from urllib.parse import quote
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from sqlalchemy import and_, create_engine
from sqlalchemy.orm import sessionmaker
from core.ai.ai import call_gemini_with_text, get_exa_search
from core.database.database import get_db_session
from core.database.models import DataEntry, User
from core.notifications.emails import is_valid_email, make_click_token, make_unsub_token, send_email

load_dotenv()

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

SERVER_URL = os.getenv("SERVER_URL")

BASE_DIR = Path(__file__).resolve().parent
DIGEST_TEMPLATE_PATH = BASE_DIR.parent / "templates" / "template_digest.html"

def get_all_data(user_id):
    # Current period rows (full)
    now_rows: List[DataEntry] = session.query(DataEntry) \
        .filter(
            and_(
                DataEntry.user_id == user_id
            )
        ) \
        .order_by(DataEntry.timestamp.desc()) \
        .limit(1000) \
        .all()

    return now_rows

def build_tags_yaml(now_rows, now=None, top_k_similar=10):
    now = now or datetime.now(timezone.utc)

    def to_dt(ts):
        if isinstance(ts, datetime):
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            return None

    def extract_tags(raw):
        # Accept list/tuple/set, JSON string, python-literal string, or comma-separated string.
        if raw is None:
            return []
        if isinstance(raw, (list, tuple, set)):
            return [str(t) for t in raw if str(t).strip()]
        if isinstance(raw, str):
            s = raw.strip()
            # JSON dict or list?
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    out = []
                    for key in ("tags", "keywords", "themes"):
                        v = obj.get(key)
                        if isinstance(v, (list, tuple, set)):
                            out.extend([str(t) for t in v if str(t).strip()])
                    if out:
                        return out
                if isinstance(obj, list):
                    return [str(t) for t in obj if str(t).strip()]
            except Exception:
                pass
            # Python literal?
            try:
                obj = ast.literal_eval(s)
                if isinstance(obj, (list, tuple, set)):
                    return [str(t) for t in obj if str(t).strip()]
            except Exception:
                pass
            # Fallback: comma-separated
            return [p for p in (t.strip() for t in s.split(",")) if p]
        return [str(raw)]

    def norm(tag: str) -> str:
        t = re.sub(r"\s+", " ", tag.strip().lower())
        return t[:256]  # guardrails

    # Gather timestamps per tag and co-occurrence
    tag_to_ts = defaultdict(list)
    co = defaultdict(Counter)

    for row in now_rows:
        ts_raw = getattr(row, "timestamp", None)
        dt = to_dt(ts_raw)
        if not dt:
            continue
        raw_tags = getattr(row, "tags", None)
        tags = [norm(t) for t in extract_tags(raw_tags)]
        # If no tags, try to mine from a 'data'/'json' field if present
        if not tags:
            for alt_field in ("data", "json", "raw", "metadata"):
                if hasattr(row, alt_field):
                    tags = [norm(t) for t in extract_tags(getattr(row, alt_field))]
                    if tags:
                        break
        # Deduplicate tags within a row to avoid inflated co-occurrence
        tags = list(dict.fromkeys(tags))
        if not tags:
            continue

        for t in tags:
            tag_to_ts[t].append(dt)
        for i, a in enumerate(tags):
            for b in tags:
                if a != b:
                    co[a][b] += 1

    def count_in(days, lst):
        cutoff = now - timedelta(days=days)
        return sum(1 for d in lst if d >= cutoff)

    # Assemble summaries
    items = []
    for tag, ts_list in tag_to_ts.items():
        ts_list.sort()
        items.append({
            "tag": tag,
            "total_freq": len(ts_list),
            "freq_in_1d": count_in(1, ts_list),
            "freq_in_7d": count_in(7, ts_list),
            "freq_in_30d": count_in(30, ts_list),
            "freq_in_6m": count_in(182, ts_list),
            "freq_in_1y": count_in(365, ts_list),
            "similar_tags": [t for t, _ in co[tag].most_common(top_k_similar)],
            "latest_timestamp": int(ts_list[-1].timestamp()),
            "earliest_timestamp": int(ts_list[0].timestamp()),
        })

    # Sort by total frequency desc, then tag asc
    items.sort(key=lambda x: (-x["total_freq"], x["tag"]))

    out = {"tags_summary": items[:10]}
    return yaml.safe_dump(out, sort_keys=False)

def get_ai_search(now_rows: List[DataEntry]):
    sys_prompt = f"""
    Generate a single line search query based on the determined persona of the user from their saved posts.
    """
    
    usr_prompt = build_tags_yaml(now_rows)
    print(f"usr_prompt\n{usr_prompt}")
    
    summary_text_out = call_gemini_with_text(sys_prompt = sys_prompt, usr_prompt = usr_prompt)
    # print(f"summary_text_out\n{summary_text_out}")
    
    search_result_out = get_exa_search(text = summary_text_out)
    # print(f"search_result_out\n{search_result_out}")

    return search_result_out

def build_user_urls(user_id: int, search_results, inline_images: dict) -> str:
    if not search_results:
        return "<li>No links saved recently</li>"

    items = []
    for idx, res in enumerate(search_results):
        url = res.url
        title = res.title

        try:
            preview = link_preview(url)
            desc = preview.description or ""
            img_url  = preview.absolute_image or ""
        except Exception:
            desc = ""
            img_url  = ""

        cid = None
        if img_url:
            try:
                r = requests.get(img_url, timeout=5)
                if r.ok and r.content:
                    cid = f"link{idx}"
                    inline_images[cid] = r.content
            except Exception:
                pass

        # tracked redirect
        link_token = make_click_token(user_id=user_id, url=url, source="digest")
        tracked_url = f"{SERVER_URL}/api/click?t={quote(link_token)}"

        # Build HTML card for each link
        block = f"""
        <div style="margin-bottom:16px; list-style:none;">
            <a href="{tracked_url}" style="color:#deff96; font-weight:bold; font-size:15px; text-decoration:none;">{title}</a><br>
            <span style="color:#bbb; font-size:13px;">{desc}</span><br>
            {f'<img src="cid:{cid}" alt="" style="max-width:100%; margin-top:8px;">' if cid else ""}
        </div>
        """
        items.append(block)
    
    return ("[USER_URLS]", "\n".join(items))

def generate_digest(user_id: int, unsubscribe_url: str):
    # Get all data
    now_rows = get_all_data(user_id)

    # Collect replacements
    replacements = {}
    inline_images = {}

    # AI summary
    search_res = get_ai_search(now_rows)

    # User URLs
    k, v = build_user_urls(user_id, search_res, inline_images)
    replacements[k] = v

    # add icon
    with open("assets/icon.png", "rb") as f:
        inline_images["icon"] = f.read()
    
    # Unsub
    replacements["[UNSUB_URL]"] = unsubscribe_url

    # Load template
    with open(DIGEST_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_template = f.read()

    # Replace placeholders
    for key, val in replacements.items():
        html_template = html_template.replace(key, val)
    
    return html_template, inline_images

def run_once():
    # Get all users that have digest email enabled
    all_users = session.query(User).all()
    for user in all_users:
        # check email validity
        if not is_valid_email(user.email):
            print(f"Skipping user {user.id}: invalid or missing email ({user.email})")
            continue
        
        # check email enabled
        if not user.digest_email_enabled:
            print(f"Skipping user {user.id} cause they have digest emails disabled")
            continue

        print(f"Proceeding for user {user.id} ({user.email})")

        # last digest
        tz = ZoneInfo(user.timezone) if user.timezone else ZoneInfo("America/New_York")
        last_sent = user.last_digest_sent or 0
        last_sent_dt = datetime.fromtimestamp(last_sent, tz=UTC)

        # --- morning window (06:00–09:00 local) ---
        now_dt = datetime.now(UTC)
        local_now = now_dt.astimezone(tz)
        send_window_start = time(6, 0)
        send_window_end   = time(9, 0)
        in_window = send_window_start <= local_now.time() <= send_window_end

        due = False
        due = in_window and (last_sent_dt.date() < local_now.date())

        # due = True
        if due:
            print(f"Sending digest to {user.username} ({user.email})")

            unsub_token = make_unsub_token(user.id, user.email, "digest")
            unsubscribe_url = f"{SERVER_URL}/api/unsubscribe?t={unsub_token}"
            digest_html, inline_images = generate_digest(user.id, unsubscribe_url)
            
            if digest_html:
                send_email(
                    user_email = user.email,
                    subject = f"Your FORGOR Digest",
                    html_body = digest_html,
                    inline_images=inline_images,
                    unsubscribe_url = unsubscribe_url
                )
            else:
                print(f"No digest content generated for {user.username}")

            # update last sent timestamp
            now_ts = int(now_dt.timestamp())
            user.last_digest_sent = now_ts
            session.add(user)
        else:
            print(f"Summary not due for {user.username} ({user.email})")

    session.commit()
    session.close()

# ---------- Run directly ----------

if __name__ == "__main__":
    session = get_db_session()
    
    try:
        run_once()
    except Exception as e:
        logger.exception(f"Error creating digest: {e}")
        raise
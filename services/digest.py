# digest.py

import logging
from datetime import datetime, time, timedelta, date, UTC
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import markdown
from sqlalchemy import and_, text, create_engine
from sqlalchemy.orm import sessionmaker
from core.ai.ai import call_gemini_with_text, get_exa_search
from core.database.models import DataEntry, User
from core.notifications.emails import is_valid_email, make_unsubscribe_token, send_email
from core.utils.config import Config

load_dotenv()

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

engine = create_engine(Config.ENGINE_URL)
Session = sessionmaker(bind=engine)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR.parent / "templates" / "template_digest.html"

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

def get_ai_search(now_rows: List[DataEntry]):
    sys_prompt = f"""
    Generate a single line search query based on the determined persona of the user from their saved posts.
    """
    
    usr_prompt = str([f"{row.id} - {row.tags}" for row in now_rows])
    # logger.info(f"usr_prompt\n{usr_prompt}")
    
    summary_text_out = call_gemini_with_text(sys_prompt = sys_prompt, usr_prompt = usr_prompt)
    # logger.info(f"summary_text_out\n{summary_text_out}")
    
    search_result_out = get_exa_search(text = summary_text_out)
    # logger.info(f"search_result_out\n{search_result_out}")

    return search_result_out

def build_user_urls(search_results) -> str:
    if not search_results:
        return "<li>No links saved recently</li>"

    items = []
    for res in search_results:
        url = res.url
        title = res.title
        items.append(f'<li><a href="{url}" style="color:#deff96;">{title}</a></li>')
    
    return ("[USER_URLS]", "\n".join(items))

def generate_digest(user_id: int, unsubscribe_url: str):
    # Get all data
    now_rows = get_all_data(user_id)

    # Collect replacements
    replacements = {}

    # AI summary
    search_res = get_ai_search(now_rows)

    # User URLs
    k, v = build_user_urls(search_res)
    replacements[k] = v
    
    # Unsub
    replacements["[UNSUB_URL]"] = unsubscribe_url

    # Load template
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_template = f.read()

    # Replace placeholders
    for key, val in replacements.items():
        html_template = html_template.replace(key, val)
    
    return html_template

def run_once():
    # Get all users that have digest email enabled
    all_users = session.query(User).all()
    for user in all_users:
        # check email validity
        if not is_valid_email(user.email):
            print(f"Skipping user {user.id}: invalid or missing email ({user.email})")
            continue
        
        # check email enabled
        if not user.digest_email_enabled == False:
            logger.info(f"Skipping user {user.id} cause they have digest emails disabled")
            continue

        logger.info(f"Proceeding for user {user.id} ({user.email})")

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
            logger.info(f"Sending digest to {user.username} ({user.email})")

            token = make_unsubscribe_token(user.id, user.email, "digest")
            unsubscribe_url = f"https://forgor.space/api/unsubscribe?t={token}"
            digest_html = generate_digest(user.id, unsubscribe_url)
            if digest_html:
                send_email(
                    user_email = user.email,
                    subject = f"Your FORGOR Digest",
                    html_body = digest_html,
                    unsubscribe_url = unsubscribe_url
                )
            else:
                logger.warning(f"No digest content generated for {user.username}")

            # update last sent timestamp
            now_ts = int(now_dt.timestamp())
            user.last_digest_sent = now_ts
            session.add(user)
        else:
            logger.debug(f"Summary not due for {user.username} ({user.email})")

    session.commit()
    session.close()

# ---------- Run directly ----------

if __name__ == "__main__":
    session = Session()
    
    try:
        run_once()
    except Exception as e:
        logger.exception(f"Error creating digest: {e}")
        raise
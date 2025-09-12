# summary.py

import os, logging, markdown, argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Tuple
from sqlalchemy import and_
from core.content.images import create_pinterest_mosaic
from core.database.database import get_db_session
from core.database.models import DataEntry, User
from core.notifications.emails import is_valid_email, make_unsub_token, send_email
from core.ai.ai import call_gemini_with_text
from core.utils.config import Config

load_dotenv()

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

SERVER_URL = os.getenv("SERVER_URL")

BASE_DIR = Path(__file__).resolve().parent
SUMMARY_TEMPLATE_PATH = BASE_DIR.parent / "templates" / "template_summary.html"

# ---------- Main Functions ----------

def get_all_data(user_id, period_start, period_end):
    # Current period rows (full)
    now_rows: List[DataEntry] = session.query(DataEntry) \
        .filter(
            and_(
                DataEntry.user_id == user_id,
                DataEntry.timestamp >= period_start,
                DataEntry.timestamp < period_end
            )
        ) \
        .order_by(DataEntry.timestamp.desc()) \
        .limit(1000) \
        .all()

    return now_rows

def get_ai_summary(now_rows: List[DataEntry], period: str):
    sys_prompt = Config.SUMMARY_AI_SYSTEM_PROMPT.replace("<PERIOD>", period)
    # print(f"sys_prompt\n{sys_prompt}")
    
    usr_prompt = str([f"{row.id} - {row.tags}" for row in now_rows])
    # print(f"usr_prompt\n{usr_prompt}")
    
    out = call_gemini_with_text(sys_prompt = sys_prompt, usr_prompt = usr_prompt)
    out_html = markdown.markdown(out)
    print(f"out_html\n{out_html}")
    
    return ("[AI_SUMMARY]", out_html)

def get_img_mosaic(now_rows: List[DataEntry]):
    images = [row.file_path for row in now_rows]
    img_bytes  = create_pinterest_mosaic(images, final_size=(1200, 400))
    cid = "mosaic"
    html_img_tag = f'<img src="cid:{cid}" alt="Mosaic" style="max-width:100%;">'
    return ("[IMAGE_PLACEHOLDER]", html_img_tag, {cid: img_bytes})

def epoch_range(period: str) -> Tuple[int,int]:
    now = datetime.now(UTC)
    
    if period == "daily":
        start = now - timedelta(hours=24)
    elif period == "weekly":
        start = now - timedelta(days=7)
    elif period == "monthly":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=365)
    
    return int(start.timestamp()), int(now.timestamp())

def generate_summary(user_id: int, unsubscribe_url: str, period="weekly"):
    # Get time range
    period_start, period_end = epoch_range(period)

    # Get all data
    now_rows = get_all_data(user_id, period_start, period_end)

    # Collect replacements + inline images
    replacements = {}
    inline_images = {}

    # AI summary
    k, v = get_ai_summary(now_rows, period)
    replacements[k] = v

    # Mosaic
    k, v, imgs = get_img_mosaic(now_rows)
    replacements[k] = v
    inline_images.update(imgs)

    # Range
    start_dt = datetime.fromtimestamp(period_start, tz=UTC)
    if period == "daily":
        period_title = "DAILY SUMMARY"
        sub = f"Day of {start_dt.strftime('%Y-%m-%d')}"
    elif period == "weekly":
        period_title = "WEEKLY SUMMARY"
        sub = f"Week of {start_dt.strftime('%Y-%m-%d')}"
    elif period == "monthly":
        period_title = "MONTHLY SUMMARY"
        sub = f"Month of {start_dt.strftime('%Y-%m-%d')}"
    else:
        period_title = f"{period.upper()} SUMMARY"
        sub = f"{start_dt.strftime('%Y-%m-%d')}"
    replacements["[TIME_RANGE_TITLE]"] = period_title
    replacements["[TIME_RANGE_SUB]"] = sub

    # add icon
    with open("assets/icon.png", "rb") as f:
        inline_images["icon"] = f.read()
    
    # Unsub
    replacements["[UNSUB_URL]"] = unsubscribe_url

    # Load template
    with open(SUMMARY_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_template = f.read()

    # Replace placeholders
    for key, val in replacements.items():
        html_template = html_template.replace(key, val)
    
    return html_template, inline_images

def run_once():
    # Get all users
    all_users = session.query(User).all()
    for user in all_users:
        # check email validity
        if not is_valid_email(user.email):
            print(f"Skipping user {user.id}: invalid or missing email ({user.email})")
            continue
        
        # check email enabled
        if not user.summary_email_enabled:
            print(f"Skipping user {user.id} cause they have summary emails disabled")
            continue

        print(f"Proceeding for user {user.id} ({user.email})")

        # decide if summary is due
        due = False
        last_sent = user.last_summary_sent or 0
        freq = user.summary_frequency
        freq_name = freq.name if freq else "unspecified"
        now = int(datetime.now(UTC).timestamp())
        print(f"freq_name: {freq_name}")

        if freq_name == "daily":
            due = now - last_sent >= 86400  # 1 day
        elif freq_name == "weekly":
            due = now - last_sent >= 604800  # 7 days
        elif freq_name == "monthly":
            due = now - last_sent >= 2592000 # ~30 days
        print(f"due: {due}")

        # due = True
        if due:
            print(f"Sending summary to {user.username} ({user.email}) [{freq_name}]")

            unsub_token = make_unsub_token(user.id, user.email, "digest")
            unsubscribe_url = f"{SERVER_URL}/api/unsubscribe?t={unsub_token}"
            summary_content, inline_images = generate_summary(user_id=user.id, unsubscribe_url=unsubscribe_url, period=freq_name)
            
            if summary_content:
                send_email(
                    user_email = user.email,
                    subject = f"Your FORGOR Summary",
                    html_body = summary_content,
                    inline_images=inline_images,
                    unsubscribe_url = unsubscribe_url
                )
            else:
                logger.warning(f"No summary content generated for {user.username}")

            # update last sent timestamp
            user.last_summary_sent = now
            session.add(user)
        else:
            print(f"Summary not due for {user.username} ({user.email}) [{freq_name}] - {now - last_sent}s")

    session.commit()
    session.close()

# ---------- Run directly ----------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-user", type=int, help="Force send summary to a specific user ID")
    args = parser.parse_args()

    session = get_db_session()

    try:
        if args.force_user:
            user = session.query(User).filter_by(id=args.force_user).first()
            if user and is_valid_email(user.email):
                unsub_token = make_unsub_token(user.id, user.email, "summary")
                unsubscribe_url = f"{SERVER_URL}/api/unsubscribe?t={unsub_token}"
                summary_content, inline_images = generate_summary(user_id=user.id, unsubscribe_url=unsubscribe_url, period="daily")

                if summary_content:
                    send_email(
                        user_email = user.email,
                        subject = f"Your FORGOR Summary",
                        html_body = summary_content,
                        inline_images=inline_images,
                        unsubscribe_url = unsubscribe_url
                    )
                    print(f"Forced summary sent to user {user.id} ({user.email})")
                else:
                    print("Summary generation failed.")
            else:
                print("Invalid or missing user/email.")
        else:
            run_once()
    except Exception as e:
        logger.exception(f"Error creating summary: {e}")
        raise
    finally:
        session.close()
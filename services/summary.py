# summary.py

import logging, markdown
from datetime import datetime, UTC, timedelta
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from typing import List, Tuple
from sqlalchemy import func, and_, create_engine
from core.content.images import create_pinterest_mosaic
from core.database.models import DataEntry, User
from core.notifications.emails import is_valid_email, send_email
from core.utils.config import Config
from core.ai.ai import call_gemini_with_text

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR.parent / "templates" / "summary_template.html"

# ---------- Helper Functions ----------

def epoch_range(period: str) -> Tuple[int,int,int,int]:
    now = datetime.now(UTC)
    if period == "weekly":
        start = now - timedelta(days=7)
        prev_start = start - timedelta(days=7)
    else:  # monthly
        start = now - timedelta(days=30)
        prev_start = start - timedelta(days=30)
    return int(start.timestamp()), int(now.timestamp()), int(prev_start.timestamp()), int(start.timestamp())

# ---------- Main Functions ----------

def get_all_data(user_id, period_start, period_end, prev_start, prev_end):
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
    
    # Previous period count (for % change)
    prev_cnt = session.query(func.count(DataEntry.id)).filter(
        and_(DataEntry.user_id == user_id,
             DataEntry.timestamp >= prev_start,
             DataEntry.timestamp < prev_end)
    ).scalar() or 0

    # Total archive
    total_cnt = session.query(func.count(DataEntry.id)).filter(
        DataEntry.user_id == user_id
    ).scalar() or 0

    return (now_rows, prev_cnt, total_cnt)

def get_ai_summary(now_rows: List[DataEntry], period: str):
    sys_prompt = f"""
    Generate a summary based on the user's saved posts in the past {period} period.
    """
    print(f"sys_prompt\n{sys_prompt}")
    usr_prompt = str([f"{row.id} - {row.tags}" for row in now_rows])
    print(f"usr_prompt\n{usr_prompt}")
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

# ---------- Summary Generator ----------

def generate_summary(user_id: int, period="weekly"):
    # Get time range
    period_start, period_end, prev_start, prev_end = epoch_range(period)

    # Get all data
    now_rows, prev_cnt, total_cnt = get_all_data(user_id, period_start, period_end, prev_start, prev_end)

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
    start_str = datetime.fromtimestamp(period_start, tz=UTC).strftime("%Y-%m-%d")
    end_str   = datetime.fromtimestamp(period_end, tz=UTC).strftime("%Y-%m-%d")
    replacements["TIME_RANGE"] = f"THIS {period.upper()}: {start_str} → {end_str}"

    # Load template
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_template = f.read()

    # Replace placeholders
    for key, val in replacements.items():
        html_template = html_template.replace(key, val)
    
    return html_template, inline_images

# ---------- Run directly ----------

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

engine = create_engine(Config.ENGINE_URL)
Session = sessionmaker(bind=engine)

if __name__ == "__main__":
    session = Session()

    try:
        now = int(datetime.now(UTC).timestamp())
        
        all_users = session.query(User).all()

        for user in all_users:
            # check email validity
            if not is_valid_email(user.email):
                print(f"Skipping user {user.id}: invalid or missing email ({user.email})")
                continue
            
            freq_name = user.frequency.name if user.frequency else "unspecified"

            # decide if summary is due
            last_sent = user.last_summary_sent or 0
            due = False

            if freq_name == "daily":
                due = now - last_sent >= 86400  # 1 day
            elif freq_name == "weekly":
                due = now - last_sent >= 604800  # 7 days
            elif freq_name == "monthly":
                due = now - last_sent >= 2592000 # ~30 days

            if due:
                print(f"Sending summary to {user.username} ({user.email}) [{freq_name}]")

                summary_content, inline_images = generate_summary(user_id=user.id, period=freq_name)
                
                if summary_content:
                    send_email(
                        user_email = user.email,
                        subject = f"Your {freq_name} FORGOR Summary",
                        html_body = summary_content,
                        inline_images=inline_images
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
            
    except Exception as e:
        print(f"Error creating summary: {e}")
        session.close()
# emails.py

from email.mime.image import MIMEImage
import os
import logging
import base64
import re
import smtplib
from io import BytesIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from email.mime.base import MIMEBase
from email import encoders
import traceback
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SMTP_SERVER = "mail.smtp2go.com"
SMTP_PORT   = int(os.getenv("SMTP_PORT", "2525"))
SMTP_USER   = os.getenv("SMTP2GO_SMTP_USER")
SMTP_PASS   = os.getenv("SMTP2GO_SMTP_PASS")
APP_SECRET  = os.getenv("APP_SECRET_KEY")

FROM_EMAIL  = "nikhil@forgor.space"

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

assert SMTP_USER and SMTP_PASS, "Missing SMTP2GO_SMTP_USER/SMTP2GO_SMTP_PASS"

# ---------------------------------- UNSUBS ------------------------------------

def make_unsubscribe_token(user_id: int, email: str, source: str) -> str:
    s = URLSafeTimedSerializer(APP_SECRET)
    return s.dumps({"uid": user_id, "e": email, "s": source})

def verify_unsubscribe_token(token: str, max_age: int = 60*60*24*30):
    s = URLSafeTimedSerializer(APP_SECRET)
    try:
        return s.loads(token, max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None

def _append_unsubscribe(html_body: str, text_body: str, unsubscribe_url: str):
    if unsubscribe_url:
        # plain text
        text_body = (text_body or "") + f"\n\nTo unsubscribe: {unsubscribe_url}"
        # html - small footer link
        unsubscribe_html = (
            '<p style="font-size:12px;color:#888;margin-top:20px;">'
            f'<a href="{unsubscribe_url}" style="color:#deff96;">Unsubscribe</a>'
            '</p>'
        )
        html_body = html_body + unsubscribe_html
    return html_body, text_body

# ---------------------------------- HELPERS ------------------------------------

def is_valid_email(email: str) -> bool:
    if not email:
        return False
    return EMAIL_REGEX.match(email) is not None

# ---------------------------------- SENDING ------------------------------------

def send_email(user_email: str, subject: str, html_body: str, text_body: str = None, inline_images: dict = None, unsubscribe_url: str = None):
    """
    Sends a backup email with ZIP attachment via raw SMTP/MIME.
    """
    try:
        # Outer "related" container for HTML + inline images
        msg = MIMEMultipart("related")
        msg["From"] = FROM_EMAIL
        msg["To"] = user_email
        msg["Subject"] = subject

        if unsubscribe_url:
            msg["List-Unsubscribe"] = f"<{unsubscribe_url}>, <mailto:unsubscribe@forgor.space?subject=unsubscribe>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        # Alternative: plain-text and HTML
        alt = MIMEMultipart("alternative")
        if not text_body:
            # very naive fallback: strip tags
            text_body = re.sub(r"<[^>]+>", "", html_body)
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)

        # Inline images
        if inline_images:
            for cid, img_bytes in inline_images.items():
                img_part = MIMEImage(img_bytes, _subtype="jpeg")
                img_part.add_header("Content-ID", f"<{cid}>")
                img_part.add_header("Content-Disposition", "inline", filename=f"{cid}.jpg")
                msg.attach(img_part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [user_email], msg.as_string())

        logger.info(f"Email sent successfully to {user_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        traceback.format_exc()
        return False

def send_email_with_zip(user_email: str, subject: str, html_body: str, zip_bytes: BytesIO, text_body: str = None):
    """
    Sends a backup email with ZIP attachment via raw SMTP/MIME.
    """
    try:
        msg = MIMEMultipart()
        msg["From"] = FROM_EMAIL
        msg["To"] = user_email
        msg["Subject"] = subject

        if not text_body:
            text_body = re.sub(r"<[^>]+>", "", html_body)

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)

        # Attachment
        part = MIMEBase("application", "zip")
        part.set_payload(zip_bytes.getvalue())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="FORGOR_backup.zip"',
        )
        msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [user_email], msg.as_string())

        logger.info(f"Email sent successfully to {user_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
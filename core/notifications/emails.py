from email.mime.image import MIMEImage
import os
import logging
import base64
import re
import smtplib
from io import BytesIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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

FROM_EMAIL  = "nikhil@forgor.space"

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

assert SMTP_USER and SMTP_PASS, "Missing SMTP2GO_SMTP_USER/SMTP2GO_SMTP_PASS"

def is_valid_email(email: str) -> bool:
    if not email:
        return False
    return EMAIL_REGEX.match(email) is not None

def send_email(user_email: str, subject: str, html_body: str, text_body: str = None, inline_images: dict = None):
    """
    Sends a backup email with ZIP attachment via raw SMTP/MIME.
    """
    try:
        # Outer "related" container for HTML + inline images
        msg = MIMEMultipart("related")
        msg["From"] = FROM_EMAIL
        msg["To"] = user_email
        msg["Subject"] = subject

        # Alternative: plain-text and HTML
        alt = MIMEMultipart("alternative")
        if not text_body:
            # very naive fallback: strip tags
            text_body = re.sub(r"<[^>]+>", "", html_body)
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)
        msg.attach(alt)

        # Inline images
        if inline_images:
            for cid, img_bytes in inline_images.items():
                img_part = MIMEImage(img_bytes)
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
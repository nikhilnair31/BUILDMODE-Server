import os
import logging
import base64
import smtplib
from io import BytesIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SMTP_SERVER = "mail.smtp2go.com"
SMTP_PORT   = int(os.getenv("SMTP_PORT", "2525"))
SMTP_USER   = os.getenv("SMTP2GO_SMTP_USER")
SMTP_PASS   = os.getenv("SMTP2GO_SMTP_PASS")

FROM_EMAIL  = "nikhil@forgor.space"

assert SMTP_USER and SMTP_PASS, "Missing SMTP2GO_SMTP_USER/SMTP2GO_SMTP_PASS"

def send_email_with_zip(user_email: str, subject: str, body: str, zip_bytes: BytesIO):
    """
    Sends a backup email with ZIP attachment via raw SMTP/MIME.
    """
    try:
        msg = MIMEMultipart()
        msg["From"] = FROM_EMAIL
        msg["To"] = user_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

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
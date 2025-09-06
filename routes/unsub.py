# unsub.py

import logging
from pathlib import Path
from routes import unsub_bp
from flask import request, abort, make_response
from sqlalchemy.orm import Session
from core.notifications.emails import verify_unsubscribe_token
from core.database.models import User
from core.database.database import engine  # or your session factory

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR.parent / "templates" / "template_ubsub.html"

SUCCESS_HTML = (
    "<!doctype html><meta charset='utf-8'>"
    "<body style='font-family:Arial;background:#1e1c2c;color:#fff'>"
    "<div style='max-width:600px;margin:40px auto'>"
    "<h2 style='color:#deff96'>Unsubscribed</h2>"
    "<p>You will no longer receive this email.</p>"
    "</div></body>"
)

def _apply_unsub(uid: int, email: str, source: str|None):
    with Session(bind=engine) as s:
        user = s.query(User).get(uid)
        if not user or user.email != email:
            abort(400, "Token/user mismatch")
        if source == "digest":
            user.digest_email_enabled = False
        elif source == "summary":
            user.summary_email_enabled = False
        else:
            user.digest_email_enabled = False
            user.summary_email_enabled = False
        s.add(user); s.commit()

@unsub_bp.route("/unsubscribe", methods=["GET","POST","HEAD","OPTIONS"])
def unsubscribe():
    # RFC 8058 one-click POST
    if request.method == "POST":
        token = request.args.get("t")
        data = verify_unsubscribe_token(token)
        if not data: abort(400, "Invalid or expired token")
        _apply_unsub(data["uid"], data["e"], data.get("s"))
        return ("", 204)

    # Human GET click
    token = request.args.get("t")
    data = verify_unsubscribe_token(token)
    if not data: abort(400, "Invalid or expired token")
    _apply_unsub(data["uid"], data["e"], data.get("s"))
    # ubsub_html = open(TEMPLATE_PATH)
    resp = make_response(SUCCESS_HTML, 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    
    return resp

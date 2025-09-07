# tracking.py

import logging
from pathlib import Path
from routes import tracking_bp
from flask import request, abort, make_response, redirect
from core.notifications.emails import verify_link_token
from core.database.models import LinkInteraction, User
from core.database.database import get_db_session  # or your session factory

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR.parent / "templates" / "template_ubsub.html"

@tracking_bp.route("/unsubscribe", methods=["GET","POST","HEAD","OPTIONS"])
def unsubscribe():
    token = request.args.get("t")
    if not token:
        abort(400, "Missing token")

    data = verify_link_token(token)
    if not data:
        abort(400, "Invalid or expired token")

    uid = int(data["uid"])
    email = data["e"]
    source = data["s"]
    
    session = get_db_session()
    try:
        user = session.query(User).get(uid)
        if not user or user.email != email:
            abort(400, "Token/user mismatch")
        
        if source == "digest":
            user.digest_email_enabled = False
        elif source == "summary":
            user.summary_email_enabled = False
        else:
            user.digest_email_enabled = False
            user.summary_email_enabled = False
        
        session.add(user)
        session.commit()

        # Handle machine POST (RFC 8058)
        if request.method == "POST":
            return ("", 204)

        # Human GET
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            html_content = f.read()

        resp = make_response(html_content, 200)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
    
    finally:
        session.close()
    
    return resp

@tracking_bp.route("/click", methods=["GET","POST","HEAD","OPTIONS"])
def track_click():
    token = request.args.get("t")
    if not token:
        abort(400, "Missing token")
    logger.info(f"token: {token}")
    
    data = verify_link_token(token)
    if not data:
        abort(400, "Invalid or expired token")
    logger.info(f"data: {data}")

    uid = int(data["uid"])
    url = data["url"]

    session = get_db_session()
    try:
        li = LinkInteraction(
            user_id=uid, 
            digest_url=url
        )
        logger.info(f"li: {li}")
        session.add(li)
        session.commit()
    
    except Exception:
        session.rollback()
    
    finally:
        session.close()

    return redirect(url, code=302)
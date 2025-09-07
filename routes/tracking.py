# tracking.py

import logging
from pathlib import Path
from core.utils.decoraters import token_required
from core.utils.logs import error_response
from routes import tracking_bp
from flask import request, abort, make_response, redirect
from core.notifications.emails import verify_link_token
from core.database.models import DataEntry, LinkInteraction, PostInteraction, User
from core.database.database import get_db_session  # or your session factory

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
UNSUB_TEMPLATE_PATH = BASE_DIR.parent / "templates" / "template_ubsub.html"

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
        with open(UNSUB_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            html_content = f.read()

        resp = make_response(html_content, 200)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"

        logger.info(f"Unsubscribed user: {user.id}!")
    
    finally:
        session.close()
    
    return resp

@tracking_bp.route("/click", methods=["GET","POST","HEAD","OPTIONS"])
def track_click():
    token = request.args.get("t")
    if not token:
        abort(400, "Missing token")
    # logger.info(f"token: {token}")
    
    data = verify_link_token(token)
    if not data:
        abort(400, "Invalid or expired token")
    # logger.info(f"data: {data}")

    uid = int(data["uid"])
    url = data["url"]

    session = get_db_session()
    try:
        li = LinkInteraction(
            user_id=uid, 
            digest_url=url
        )
        session.add(li)
        session.commit()

        logger.info(f"Tracked link!")
    
    except Exception:
        session.rollback()
    
    finally:
        session.close()

    return redirect(url, code=302)

@tracking_bp.route('/insert-post-interaction', methods=['PUT'])
@token_required
def insert_post_interaction(current_user):
    logger.info(f"Inserting post interaction for user: {current_user.id}")

    session = get_db_session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        data = request.get_json(silent=True) or {}
        try:
            file_id = int(data.get("fileId", 0))
        except (TypeError, ValueError):
            return error_response("Invalid or missing 'fileId'", 400)

        query_text = (data.get("query") or "").strip()
        if not query_text:
            return error_response("Missing 'query' field", 400)

        # Ensure referenced data entry exists
        data_entry = session.query(DataEntry).get(file_id)
        if not data_entry:
            return error_response(f"Data entry {file_id} not found", 404)

        # Create new interaction
        interaction = PostInteraction(
            user_id=user.id,
            data_id=data_entry.id,
            user_query=query_text,
        )
        session.add(interaction)
        session.commit()

        logger.info(f"Inserted post interaction {interaction.id} for user {user.id}")
        return {"message": "Inserted of post interaction", "id": interaction.id}, 200

    except Exception as e:
        logger.error(f"Error inserting post interaction for {current_user.id}: {e}")
        session.rollback()
        return error_response("Failed to inserting post interaction", 500)

    finally:
        session.close()

@tracking_bp.route('/insert-link-interaction', methods=['PUT'])
@token_required
def insert_link_interaction(current_user):
    logger.info(f"Inserting link interaction for: {current_user.id}")

    session = get_db_session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        data = request.get_json(silent=True) or {}
        # logger.info(f"data: {data}")
        
        try:
            url = (data.get("url") or "").strip()
        except (TypeError, ValueError):
            return error_response("Missing 'url' field", 400)

        # Create new interaction
        interaction = LinkInteraction(
            user_id=user.id,
            digest_url=url,
        )
        session.add(interaction)
        session.commit()

        logger.info(f"Inserted link interaction {interaction.id} for user {user.id}")
        return {"message": "Inserted of link interaction", "id": interaction.id}, 200

    except Exception as e:
        logger.error(f"Error inserting link interaction for {current_user.id}: {e}")
        session.rollback()
        return error_response("Failed to inserting link interaction", 500)

    finally:
        session.close()

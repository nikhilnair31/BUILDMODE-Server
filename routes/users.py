# user_management.py

import logging
from flask import request, jsonify
from core.utils.data import _safe_unlink
from routes import users_bp
from core.utils.middleware import limiter
from core.notifications.emails import verify_link_token
from core.database.database import get_db_session
from core.database.models import DataEntry, Frequency, StagingEntry, User
from core.utils.logs import error_response
from core.utils.decoraters import token_required, get_user_upload_info

logger = logging.getLogger(__name__)

@users_bp.route('/get_saves_left', methods=['GET'])
# @limiter.limit("2 per second")
@token_required
def get_saves_left(current_user):
    try:
        info, error_response_obj, status_code, session = get_user_upload_info(current_user)
        
        if error_response_obj:
            session.close()
            return error_response_obj, status_code
        
        return jsonify(info), 200
    finally:
        session.close()

@users_bp.route('/summary-frequency', methods=['GET'])
# @limiter.limit("2 per second")
@token_required
def get_summary_frequency(current_user):
    session = get_db_session()
    try:
        user = session.query(User).filter(User.id == current_user.id).first()
        if not user:
            return error_response("User not found", 404)
        return {"summary_index": user.summary_frequency_id}, 200

    except Exception as e:
        logger.error(f"Error getting summary frequency for {current_user.id}: {e}")
        return error_response("Error getting summary frequency", 500)
    
    finally:
        session.close()

@users_bp.route('/digest-enabled', methods=['GET'])
# @limiter.limit("2 per second")
@token_required
def get_digest_enabled(current_user):
    session = get_db_session()
    try:
        user = session.query(User).filter(User.id == current_user.id).first()
        if not user:
            return error_response("User not found", 404)
        return {"digest_enabled": user.digest_email_enabled}, 200
    
    except Exception as e:
        logger.error(f"Error getting digest enabled for {current_user.id}: {e}")
        return error_response("Error getting digest enabled", 500)
    
    finally:
        session.close()

@users_bp.route('/account_delete', methods=['DELETE'])
@token_required
def account_delete(current_user):
    logger.info(f"Deleting account for: {current_user.id}")

    session = get_db_session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        # 1) Load records to collect file paths BEFORE bulk deletes
        staging_entries = session.query(StagingEntry).filter_by(user_id=user.id).all()
        data_entries    = session.query(DataEntry).filter_by(user_id=user.id).all()

        # 2) Delete files on disk
        removed_files = 0
        for s in staging_entries:
            if _safe_unlink(s.file_path):
                removed_files += 1

        for d in data_entries:
            if _safe_unlink(d.file_path):
                removed_files += 1
            if _safe_unlink(d.thumbnail_path):
                removed_files += 1

        # 3) Bulk delete DB rows + user (faster than per-row delete)
        staging_deleted = session.query(StagingEntry).filter_by(user_id=user.id).delete(synchronize_session=False)
        data_deleted    = session.query(DataEntry).filter_by(user_id=user.id).delete(synchronize_session=False)
        session.delete(user)

        session.commit()

        logger.info(
            f"Deleted User {user.id}, "
            f"{staging_deleted} staging entries, "
            f"{data_deleted} data entries."
        )

        return {"message": "Account deleted successfully."}, 200

    except Exception as e:
        logger.error(f"Error deleting account {current_user.id}: {e}")
        session.rollback()
        return error_response("Failed to delete account", 500)
    
    finally:
        session.close()

@users_bp.route('/update-username', methods=['PUT'])
# @limiter.limit("1 per second")
@token_required
def update_username(current_user):
    data = request.get_json()

    session = get_db_session()
    try:
        if session.query(User).filter_by(username=data['new_username']).first():
            return error_response("Username already taken", 400)

        user = session.query(User).get(current_user.id)
        user.username = data['new_username']
        session.commit()
    finally:
        session.close()
    
    return jsonify({'message': 'Username updated'}), 200

@users_bp.route('/update-email', methods=['PUT'])
# @limiter.limit("1 per second")
@token_required
def update_email(current_user):
    data = request.get_json()

    session = get_db_session()
    try:
        if session.query(User).filter_by(email=data['new_email']).first():
            return error_response("Email already taken", 400)

        user = session.query(User).get(current_user.id)
        user.email = data['new_email']
        session.commit()
    finally:
        session.close()
    
    return jsonify({'message': 'Email updated'}), 200

@users_bp.route('/summary-frequency', methods=['PUT'])
# @limiter.limit("1 per second")
@token_required
def put_summary_frequency(current_user):
    logger.info(f"Updating summary frequency for: {current_user.id}")

    session = get_db_session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        data = request.get_json()
        if not data or "frequency" not in data:
            return error_response("Missing 'frequency' field", 400)

        # Look up frequency in DB
        freq_name = data["frequency"].strip().lower()
        freq = session.query(Frequency).filter(Frequency.name.ilike(freq_name)).first()
        if not freq:
            return error_response(f"Invalid frequency '{freq_name}'", 400)

        # Update user
        user.summary_email_enabled = (freq.name != "none")
        user.summary_frequency_id = freq.id
        session.commit()

        logger.info(f"User {user.id} summary frequency updated to {freq.name}")
        return {"message": f"Summary frequency updated to {freq.name}"}, 200

    except Exception as e:
        logger.error(f"Error updating summary frequency for {current_user.id}: {e}")
        session.rollback()
        return error_response("Failed to update summary frequency", 500)

    finally:
        session.close()

@users_bp.route('/digest-enabled', methods=['PUT'])
# @limiter.limit("1 per second")
@token_required
def put_digest_enabled(current_user):
    logger.info(f"Updating digest enabled for user: {current_user.id}")

    session = get_db_session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        data = request.get_json()
        if not data or "enabled" not in data:
            return error_response("Missing 'enabled' field", 400)

        raw_val = data["enabled"]
        if isinstance(raw_val, bool):
            enabled = raw_val
        elif isinstance(raw_val, str):
            enabled = raw_val.strip().lower() in ("true", "1", "yes", "y")
        else:
            return error_response("Invalid value for 'enabled'", 400)

        # Update user
        user.digest_email_enabled = enabled
        session.commit()

        logger.info(f"User {user.id} digest enabled updated to {enabled}")
        return {"message": f"Digest frequency updated to {enabled}"}, 200

    except Exception as e:
        logger.error(f"Error updating digest enabled for {current_user.id}: {e}")
        session.rollback()
        return error_response("Failed to update digest enabled", 500)

    finally:
        session.close()

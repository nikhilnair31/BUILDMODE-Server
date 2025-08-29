# auth.py

import jwt
import datetime
import time
import logging
from flask import request, jsonify
from routes import auth_bp
from core.database.database import get_db_session
from core.database.models import User, StagingEntry, DataEntry
from core.utils.logs import error_response
from core.utils.config import Config
from core.utils.decoraters import token_required

logger = logging.getLogger(__name__)

@auth_bp.route('/refresh_token', methods=['POST'])
# @limiter.limit("2 per second") # Limiter moved to middleware setup or passed down
def refresh_token():
    data = request.get_json()
    refresh_token = data.get('refresh_token', '')

    try:
        payload = jwt.decode(refresh_token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        e = "Refresh token has expired"
        logger.error(e)
        return error_response(e, 401)
    except jwt.InvalidTokenError:
        e = "Invalid refresh token"
        logger.error(e)
        return error_response(e, 401)

    session = get_db_session()
    user = session.query(User).get(payload['user_id'])
    if not user:
        e = f"User ID {payload['user_id']} not found"
        logger.error(e)
        return error_response(e, 404)

    new_access_token = jwt.encode(
        {
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        },
        Config.JWT_SECRET_KEY,
        algorithm='HS256'
    )

    return jsonify({'access_token': new_access_token}), 200

@auth_bp.route('/register', methods=['POST'])
# @limiter.limit("1 per second")
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    timezone = data.get('timezone', '').strip()
    
    session = get_db_session()
    try:
        if session.query(User).filter_by(username=username).first():
            logger.error(f"User {username} already exists.\n")
            return error_response("Username already exists", 400)

        new_user = User(
            username=username,
            email=email,
            timezone=timezone,
            created_at=int(time.time()),
            updated_at=int(time.time())
        )
        new_user.set_password(password)

        session.add(new_user)
        session.commit()
    finally:
        session.close()

    return jsonify({"status": "success", "message": "User registered successfully."}), 200

@auth_bp.route('/login', methods=['POST'])
# @limiter.limit("1 per second")
def login():
    data = request.get_json()

    session = get_db_session()
    try:
        user = session.query(User).filter_by(username=data['username']).first()
        if not user or not user.check_password(data['password']):
            logger.error(f"Invalid credentials for user {data['username']}.\n")
            return error_response("Invalid credentials", 401)
        logger.info(f"User {user.username} logged in successfully.\n")

        access_token = jwt.encode(
            {
                'user_id': user.id,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            }, 
            Config.JWT_SECRET_KEY, 
            algorithm='HS256'
        )
        refresh_token = jwt.encode(
            {
                'user_id': user.id,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(days=60)
            }, 
            Config.JWT_SECRET_KEY, 
            algorithm='HS256'
        )
        logger.info(f"Generated access and refresh token\n")
        
        return jsonify(
            {
                'access_token': access_token, 
                'refresh_token': refresh_token
            }
        ), 200
    finally:
        session.close()

@auth_bp.route('/account_delete', methods=['DELETE'])
def account_delete(current_user):
    logger.info(f"\nDeleting account for: {current_user.id}\n")
    
    session = get_db_session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)
    
    try:
        staging_deleted = session.query(StagingEntry).filter_by(user_id=user.id).delete()
        data_deleted = session.query(DataEntry).filter_by(user_id=user.id).delete()
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
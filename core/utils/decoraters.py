import jwt
import time
import logging
from flask import request
from functools import wraps
from core.utils.config import Config
from core.database.database import get_db_session
from core.database.models import User, Tier, DataEntry
from core.utils.logs import error_response
from core.content.parser import timezone_to_start_of_day_ts

logger = logging.getLogger(__name__)

def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            e = "Token is missing or invalid"
            logger.error(e)
            return error_response(e, 401)
        
        try:
            data = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
            # logger.info(f"Decoded token payload: {data}")
        except jwt.ExpiredSignatureError:
            e = "Token has expired"
            logger.error(e)
            return error_response(e, 401)
        except jwt.InvalidTokenError:
            e = "Invalid token"
            logger.error(e)
            return error_response(e, 401)
        except Exception as e:
            e = f"Error decoding token: {e}"
            logger.error(e)
            return error_response(e, 500)

        session = get_db_session()
        try:
            user = session.query(User).filter_by(id=data['user_id']).first()
            # logger.info(f"user: {user}")
            if not user:
                e = f"User ID {data['user_id']} not found"
                logger.error(e)
                return error_response(e, 401)
        finally:
            session.close()

        return f(user, *args, **kwargs)
    return wrapper

def save_limit_required(f):
    @wraps(f)
    def wrapper(current_user, *args, **kwargs):
        info, error, status_code, session = get_user_upload_info(current_user)
        if error:
            session.close()
            return error, status_code
        
        try:
            if current_user.username in ['admin', 'root', 'superuser', 'nik', 'testing']:
                logger.info("Admin user detected, skipping save limit check.")
                return f(current_user, *args, **kwargs)
            if info['uploads_left'] <= 0:
                e = f"Daily upload limit reached for user {current_user.username} | ({info['tier_name']} - {info['daily_limit']} per day)."
                logger.warning(e)
                return error_response(e, 403)
            return f(current_user, *args, **kwargs)
        finally:
            session.close()
    return wrapper

def get_user_upload_info(current_user):
    logger.info(f"Getting upload info for user: {current_user.username}\n")
    session = get_db_session()
    try:
        tier = session.query(Tier).get(current_user.tier_id)
        if not tier:
            return None, error_response('Invalid user tier', 403), 403, session
        
        start_of_day_ts = timezone_to_start_of_day_ts(current_user.timezone)
        uploads_today = session.query(DataEntry).filter(
            DataEntry.user_id == current_user.id,
            DataEntry.timestamp >= start_of_day_ts
        ).count()
        uploads_left = max(0, tier.daily_limit - uploads_today)
        reset_in_seconds = int((start_of_day_ts + 86400) - time.time())

        output = {
            'tier_name': tier.name,
            'daily_limit': tier.daily_limit,
            'uploads_today': uploads_today,
            'uploads_left': uploads_left,
            'reset_in_seconds': reset_in_seconds,
            'start_of_day_ts': start_of_day_ts,
        }
        # logger.info(f"output: {output}\n")
        
        return output, None, None, session
    except Exception as e:
        session.close()
        raise e
# user_management.py

import logging
from flask import request, jsonify
from routes import user_management_bp
from core.database.database import get_db_session
from core.database.models import User
from core.utils.logs import error_response
from core.utils.decoraters import token_required, get_user_upload_info

logger = logging.getLogger(__name__)

@user_management_bp.route('/update-username', methods=['POST'])
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

@user_management_bp.route('/get_saves_left', methods=['GET'])
# @limiter.limit("2 per second")
@token_required
def get_saves_left(current_user):
    info, error_response_obj, status_code, session = get_user_upload_info(current_user)
    if error_response_obj:
        session.close()
        return error_response_obj, status_code

    try:
        return jsonify(info), 200
    finally:
        session.close()
from flask import jsonify

def error_response(message, status_code=400, status='error', extra=None):
    payload = {
        'status': status,
        'message': message
    }
    if extra:
        payload.update(extra)
    return jsonify(payload), status_code
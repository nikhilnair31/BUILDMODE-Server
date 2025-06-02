import logging
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import request, abort
from core.utils.config import Config

logger = logging.getLogger(__name__)

# Make limiter global
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per day", "30 per hour"]
)

def get_ip():
    # logger.info(f"request.headers: {dict(request.headers)}\n")
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    ip = forwarded_for.split(',')[0] if forwarded_for else request.headers.get('X-Real-IP', request.remote_addr)
    logger.info(f"Detected IP: {ip}")
    return ip

def apply_middleware(app):
    app.config.from_object(Config)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # Attach limiter to app
    limiter.init_app(app)

    # CORS
    CORS(app, supports_credentials=True, resources={
        r"/api/*": {
            "origins": [
                "https://forgor.space",
            ]
        }
    })

    # Before Request
    @app.before_request
    def restrict_headers():
        if request.path.startswith("/api/get_file/") or request.path.startswith("/api/get_thumbnail/"):
            return

        user_agent = request.headers.get("User-Agent", "")
        api_key = request.headers.get("X-App-Key", None)
        # logger.info(f'user_agent: {user_agent}\napi_key: {api_key}')

        # Allow during development/testing
        if "python" in user_agent.lower() or "postman" in user_agent.lower():
            return

        # Require custom header
        if not api_key or api_key != Config.APP_SECRET_KEY:
            logger.error(f"Rejected request with UA: {user_agent}, API key: {api_key}")
            abort(403, description="Forbidden: Invalid or missing headers.")

    logger.info("Middleware applied.")
    return limiter # Return limiter for potential future use or configuration
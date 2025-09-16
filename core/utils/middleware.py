# middleware.py

import logging
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import request, abort
from core.utils.config import Config

logger = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["3 per second"]
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
                "chrome-extension://dpplhhebpjhhmejgfggegelhcgfdailo"
            ],
            "allow_headers": [
                "Content-Type", "Authorization", "X-App-Key", "User-Agent", "X-Timezone"
            ],
            "methods": ["GET", "POST", "OPTIONS"]
        }
    })

    # Before Request
    @app.before_request
    def restrict_headers():
        # Always let preflight OPTIONS through
        if request.method == "OPTIONS":
            return  # Flask-CORS will handle it
            
        if request.path.startswith("/api/get_file") or request.path.startswith("/api/get_thumbnail") \
            or request.path.startswith("/api/unsubscribe") or request.path.startswith("/api/click"):
            return

        # Require custom header
        user_agent = request.headers.get("User-Agent", "")
        if not user_agent:
            logger.error(f"Rejected request with UA: {user_agent}")
            abort(403, description="Forbidden: Invalid or missing headers.")

        # logger.info(f'user_agent: {user_agent}')

    logger.info("Middleware applied.")
    return limiter # Return limiter for potential future use or configuration
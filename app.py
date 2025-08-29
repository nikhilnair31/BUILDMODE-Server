# app.py

import logging
import warnings
from flask import Flask
from routes import register_routes
from core.utils.middleware import apply_middleware
from core.database.database import init_db

warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
logging.getLogger("joblib").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize and apply middleware (CORS, Limiter, ProxyFix, Before Request)
# Note: Limiter is returned if you need to access it later, but not strictly needed for this pattern
_ = apply_middleware(app)

# Initialize Database
init_db()

# Register Blueprints
register_routes(app)
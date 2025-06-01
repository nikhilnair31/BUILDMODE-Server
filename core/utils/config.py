import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    MIA_DB_NAME = os.getenv("MIA_DB_NAME")
    MIA_DB_PASSWORD = os.getenv("MIA_DB_PASSWORD")
    THUMBNAIL_DIR = os.getenv("THUMBNAIL_DIR")
    UPLOAD_DIR = os.getenv("UPLOAD_DIR")

    # Database URL
    ENGINE_URL = f'postgresql://postgres:{MIA_DB_PASSWORD}@localhost/{MIA_DB_NAME}'

    # Add other constants here if they are configuration-like
    IMAGE_PREPROCESS_SYSTEM_PROMPT = """
        Extract a long and comprehensive list of keywords to describe the image provided. These keywords will be used for semantic search eventually. Extract things like themes, dominant/accent colors, moods along with more descriptive terms. If possible determine the app the screenshot was taken in as well. Ignore phone status information. Only output as shown below
        <tags>
        keyword1, keyword2, ...
        </tags>
    """
    ALLOWED_USER_AGENTS = [
        "YourAndroidApp/1.0",
        "python-requests",
        "PostmanRuntime",
    ]
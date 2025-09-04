import os
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

class Content(BaseModel):
    app_name: str
    engagement_counts: list[str]
    account_identifiers: list[str]
    links: list[str]
    full_ocr: str
    keywords: List[str] = Field(default_factory=list, max_items=25)
    accent_colors: list[str]
    themes: list[str]
    moods: list[str]

class Config:
    APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    MIA_DB_NAME = os.getenv("MIA_DB_NAME")
    MIA_DB_PASSWORD = os.getenv("MIA_DB_PASSWORD")
    THUMBNAIL_DIR = os.getenv("THUMBNAIL_DIR")
    UPLOAD_DIR = os.getenv("UPLOAD_DIR")
    PROXY_SERVER = os.getenv("PROXY_SERVER")
    PROXY_USERNAME = os.getenv("PROXY_USERNAME")
    PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

    # Database URL
    ENGINE_URL = f'postgresql://postgres:{MIA_DB_PASSWORD}@localhost/{MIA_DB_NAME}'

    # Add other constants here if they are configuration-like
    IMAGE_CONTENT_EXTRACTION_SYSTEM_PROMPT = """
        Extract a long and comprehensive list of comma separated keywords to describe the image provided. 
        These keywords will be used for semantic search. 
        
        Extract things like shown:
        App Name: app.
        Engagement Counts: 1.2K likes, 60 comments, 3M views, 200 bookmarks, 6 shares, 12 retweets, 12K upvotes etc.
        Account Identifiers; @account1, @account2, etc.
        Links: link1, link2, etc.
        Full OCR: content.
        Keywords: keyword1, keyword2, etc.
        Accent Colors: color1, color2, etc.
        Themes: theme1, theme2, etc.
        Moods: color1, color2, etc.

        Ignore phone status information.
    """
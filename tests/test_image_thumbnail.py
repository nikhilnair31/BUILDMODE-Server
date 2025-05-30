# test_image_thumbnail.py

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import uuid
import logging
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models import Base, DataEntry
from pre_process import generate_thumbnail
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load DB credentials
MIA_DB_NAME = os.getenv("MIA_DB_NAME")
MIA_DB_PASSWORD = os.getenv("MIA_DB_PASSWORD")
ENGINE_URL = f'postgresql://postgres:{MIA_DB_PASSWORD}@localhost/{MIA_DB_NAME}'

# Create SQLAlchemy engine and session
engine = create_engine(ENGINE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Ensure thumbnail dir exists
THUMBNAIL_DIR = './thumbnails'
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

def generate_missing_thumbnails():
    logger.info("Scanning for entries missing thumbnails...")
    entries = session.query(DataEntry).filter(
        (DataEntry.thumbnail_path == None) | (DataEntry.thumbnail_path == "")
    ).all()
    logger.info(f"Found {len(entries)} entries needing thumbnails.\n")

    updated = 0
    for entry in entries:
        file_path = entry.file_path
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            continue

        file_id = uuid.uuid4().hex
        thumbnail_rel_path = generate_thumbnail(file_path, file_id)

        if thumbnail_rel_path:
            entry.thumbnail_path = thumbnail_rel_path
            updated += 1
            logger.info(f"Generated thumbnail for: {file_path} → {thumbnail_rel_path}")
        else:
            logger.warning(f"Could not generate thumbnail for: {file_path}")

    session.commit()
    logger.info(f"✅ Updated {updated} entries with thumbnails.")

if __name__ == "__main__":
    generate_missing_thumbnails()
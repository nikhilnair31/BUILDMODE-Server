import os
import logging
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models import DataEntry  # adjust if in a different file
from pgvector.sqlalchemy import Vector
from image import (
    extract_distinct_colors
)

load_dotenv()

MIA_DB_NAME = os.getenv("MIA_DB_NAME")
MIA_DB_PASSWORD = os.getenv("MIA_DB_PASSWORD")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DB SETUP ---
DATABASE_URL = f'postgresql://postgres:{MIA_DB_PASSWORD}@localhost/{MIA_DB_NAME}'
logger.info(f"Connecting to {DATABASE_URL}\n")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

def process_all_entries():
    entries = session.query(DataEntry).all()
    if not entries:
        print("⚠️ No entries found in the data table.")
        return

    updated = 0
    skipped = 0

    for entry in entries:
        image_path = entry.imagepath
        if not os.path.isfile(image_path):
            print(f"❌ Image file not found: {image_path}")
            skipped += 1
            continue

        try:
            swatch_vec = extract_distinct_colors(image_path)
            entry.swatch_vector = swatch_vec
            updated += 1
            print(f"✅ Updated swatch vector for {image_path}")
        except Exception as e:
            print(f"❌ Error processing {image_path}: {e}")
            skipped += 1

    session.commit()
    print(f"\n🎉 Done. {updated} updated, {skipped} skipped.")

# --- RUN ---
if __name__ == "__main__":
    process_all_entries()
# scripts/update_latest_tags.py

import os
import time
import logging
import traceback
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, desc
from core.utils.config import Config
from core.database.models import DataEntry
from core.processing.background import encode_image_to_base64
from core.content.images import compress_image, generate_thumbnail
from core.ai.ai import call_llm_api, call_vec_api

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_latest_tags")

engine = create_engine(Config.ENGINE_URL)
Session = sessionmaker(bind=engine)


def update_latest_tags(limit=10):
    session = Session()
    try:
        latest_entries = (
            session.query(DataEntry)
            .order_by(desc(DataEntry.timestamp))
            .limit(limit)
            .all()
        )
        logger.info(f"Found {len(latest_entries)} latest DataEntry records")

        for entry in latest_entries:
            try:
                logger.info(f"Updating entry {entry.id} ({entry.file_path})")

                if not entry.file_path or not os.path.exists(entry.file_path):
                    logger.warning(f"File not found for entry {entry.id}, skipping")
                    continue

                # compress image again
                with open(entry.file_path, "rb") as f:
                    new_path = compress_image(f)
                if not new_path:
                    logger.error(f"Compression failed for entry {entry.id}")
                    continue

                # LLM tags
                b64_img = [encode_image_to_base64(new_path)]
                tags = call_llm_api(b64_img)
                if not tags:
                    logger.error(f"LLM extraction failed for entry {entry.id}")
                    continue

                # Embedding
                vec = call_vec_api(tags, task_type="RETRIEVAL_DOCUMENT")

                # Thumbnail regenerate (optional – refresh thumbnail if needed)
                thumb_path = generate_thumbnail(new_path)

                # Update fields
                entry.tags = tags
                entry.tags_vector = vec
                entry.thumbnail_path = thumb_path
                entry.timestamp = int(time.time())  # refresh timestamp

                session.commit()
                logger.info(f"✔ Entry {entry.id} updated successfully")

            except Exception as inner_e:
                logger.error(f"❌ Error updating entry {entry.id}: {inner_e}")
                traceback.print_exc()
                session.rollback()

    finally:
        session.close()


if __name__ == "__main__":
    update_latest_tags(limit=30)
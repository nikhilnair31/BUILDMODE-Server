# test_refresh_tags.py

import os
import time
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, desc
from core.utils.config import Config
from core.database.models import DataEntry
from core.processing.background import encode_image_to_base64
from core.content.images import compress_image, generate_thumbnail
from core.ai.ai import call_llm_api, call_vec_api

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s")
logger = logging.getLogger("test_refresh_tags")

engine = create_engine(
    Config.ENGINE_URL,
    pool_pre_ping=True,
)
Session = sessionmaker(bind=engine)

def _process_entry(entry_id: int) -> tuple[int, bool, str]:
    """
    Work on a single entry in its own session (thread-safe).
    Returns (entry_id, success, message).
    """
    session = Session()
    try:
        entry = session.query(DataEntry).get(entry_id)
        if not entry:
            return (entry_id, False, "Entry not found")

        logger.info(f"Updating entry {entry.id} ({entry.file_path})")

        if not entry.file_path or not os.path.exists(entry.file_path):
            return (entry_id, False, "File not found, skipping")

        # compress image again
        with open(entry.file_path, "rb") as f:
            new_path = compress_image(f)
        if not new_path:
            return (entry_id, False, "Compression failed")

        # LLM tags
        b64_img = [encode_image_to_base64(new_path)]
        tags = call_llm_api(b64_img)
        if not tags:
            return (entry_id, False, "LLM extraction failed")

        # Embedding
        vec = call_vec_api(tags, task_type="RETRIEVAL_DOCUMENT")

        # Thumbnail regenerate (optional – refresh thumbnail if needed)
        thumb_path = generate_thumbnail(new_path)

        # Update fields
        entry.tags = tags
        entry.tags_vector = vec
        entry.thumbnail_path = thumb_path
        # entry.timestamp = int(time.time())  # refresh timestamp

        session.commit()
        return (entry_id, True, "Updated successfully")

    except Exception as e:
        session.rollback()
        traceback.print_exc()
        return (entry_id, False, f"Exception: {e}")
    finally:
        session.close()

def update_latest_tags(limit: int = 10, max_workers: int = 4):
    """
    Parallelize per-entry processing using a ThreadPoolExecutor.

    max_workers: tune based on your CPU and external API rate limits.
                 If your LLM/vector APIs have strict QPS, lower this.
    """
    # Single session here ONLY to read the IDs to process.
    session = Session()
    try:
        latest_ids = (
            session.query(DataEntry.id)
            .filter(DataEntry.tags.contains("</tags>"))
            .order_by(desc(DataEntry.timestamp))
            .limit(limit)
            .all()
        )
        entry_ids = [row.id for row in latest_ids]
        logger.info(f"Found {len(entry_ids)} latest DataEntry records")

    finally:
        session.close()

    if not entry_ids:
        logger.info("No entries to update.")
        return

    successes = failures = 0
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="upd") as exe:
        futures = {exe.submit(_process_entry, eid): eid for eid in entry_ids}
        for fut in as_completed(futures):
            eid = futures[fut]
            try:
                _eid, ok, msg = fut.result()
                if ok:
                    successes += 1
                    logger.info(f"✔ Entry {_eid}: {msg}")
                else:
                    failures += 1
                    logger.error(f"❌ Entry {_eid}: {msg}")
            except Exception as e:
                failures += 1
                logger.error(f"❌ Entry {eid}: unhandled future exception: {e}")

    logger.info(f"Done. Success: {successes}, Failures: {failures}, Total: {len(entry_ids)}")

if __name__ == "__main__":
    # Adjust max_workers to your API/CPU limits (e.g., 2–8).
    update_latest_tags(limit=150, max_workers=6)

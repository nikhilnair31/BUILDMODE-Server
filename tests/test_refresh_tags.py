# test_refresh_tags.py

import os
import time
import logging
import traceback
import argparse
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

engine = create_engine(Config.ENGINE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

def _process_entry(entry_id: int) -> tuple[int, bool, str]:
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
        b64_img = encode_image_to_base64(new_path)
        tags = call_llm_api(b64_img)
        if not tags:
            return (entry_id, False, "LLM extraction failed")

        # Embedding
        vec = call_vec_api(tags, task_type="RETRIEVAL_DOCUMENT")

        # Thumbnail regenerate
        thumb_path = generate_thumbnail(new_path)

        # Update fields
        entry.tags = tags
        entry.tags_vector = vec
        entry.thumbnail_path = thumb_path

        session.commit()
        return (entry_id, True, "Updated successfully")

    except Exception as e:
        session.rollback()
        traceback.print_exc()
        return (entry_id, False, f"Exception: {e}")
    finally:
        session.close()

def update_latest_tags(limit: int = 10, max_workers: int = 4, replace_blank: bool = False):
    session = Session()
    try:
        q = session.query(DataEntry.id)
        if replace_blank:
            q = q.filter((DataEntry.tags == None) | (DataEntry.tags == "") | (DataEntry.tags.contains("</tags>")))
        else:
            q = q.filter(DataEntry.tags.contains("</tags>"))

        latest_ids = q.order_by(desc(DataEntry.timestamp)).limit(limit).all()
        entry_ids = [row.id for row in latest_ids]
        logger.info(f"Found {len(entry_ids)} DataEntry records to update")
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
    parser = argparse.ArgumentParser(description="Refresh tags for DataEntry records")
    parser.add_argument("-n", "--num", type=int, default=10,
                        help="Number of posts to update (default: 10)")
    parser.add_argument("-w", "--workers", type=int, default=4,
                        help="Number of worker threads (default: 4)")
    parser.add_argument("--replace-blank", action="store_true",
                        help="If set, also target entries with blank or NULL tags")

    args = parser.parse_args()
    update_latest_tags(limit=args.num, max_workers=args.workers, replace_blank=args.replace_blank)
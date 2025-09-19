# test_refresh_files.py

import os
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from core.utils.config import Config
from core.database.models import DataEntry
from core.content.images import compress_image

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("refresh_files")

engine = create_engine(Config.ENGINE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

MAX_SIZE_KB = 512
MAX_WORKERS = 4

def ensure_compressed(entry_id: int) -> tuple[int, bool, str]:
    session = Session()
    try:
        entry = session.query(DataEntry).get(entry_id)
        if not entry:
            return (entry_id, False, "Entry not found")

        fpath = entry.file_path
        if not fpath or not os.path.exists(fpath):
            return (entry_id, False, "File not found")

        size_kb = os.path.getsize(fpath) / 1024
        if size_kb > MAX_SIZE_KB or not fpath.lower().endswith(".jpg"):
            logger.info(f"[{entry_id}] Compressing {fpath} ({size_kb:.1f} KB)")
            new_path = compress_image(fpath, max_size_kb=MAX_SIZE_KB)
            if not new_path:
                return (entry_id, False, "Compression failed")

            # update DB if path changed (e.g. .png → .jpg)
            if new_path != fpath:
                entry.file_path = new_path
                session.commit()
            return (entry_id, True, f"Compressed to {os.path.getsize(new_path)/1024:.1f} KB")
        else:
            return (entry_id, True, "Already compliant")

    except Exception as e:
        session.rollback()
        traceback.print_exc()
        return (entry_id, False, f"Exception: {e}")
    finally:
        session.close()

def refresh_all_files(max_workers=MAX_WORKERS):
    session = Session()
    try:
        entries = session.query(DataEntry.id).all()
        entry_ids = [row.id for row in entries]
        logger.info(f"Found {len(entry_ids)} DataEntry records to check")
    finally:
        session.close()

    successes = failures = 0
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = {exe.submit(ensure_compressed, eid): eid for eid in entry_ids}
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
                logger.error(f"❌ Entry {eid}: exception {e}")

    logger.info(f"Done. Success={successes}, Failures={failures}")

def cleanup_orphans():
    """Remove files in UPLOAD_DIR not referenced by any DataEntry.file_path."""
    session = Session()
    try:
        valid_paths = {row.file_path for row in session.query(DataEntry.file_path).all() if row.file_path}
    finally:
        session.close()

    removed = 0
    for fname in os.listdir(Config.UPLOAD_DIR):
        fpath = os.path.join(Config.UPLOAD_DIR, fname)
        if os.path.isfile(fpath) and fpath not in valid_paths:
            os.remove(fpath)
            removed += 1
            logger.info(f"🗑 Removed orphan file {fpath}")
    logger.info(f"Cleanup done. Removed {removed} files.")

if __name__ == "__main__":
    refresh_all_files()
    cleanup_orphans()

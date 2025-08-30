# core/processing/background.py

import time, os, shutil, logging, base64, traceback
from core.utils.config import Config
from concurrent.futures import ThreadPoolExecutor
from core.database.database import get_db_session
from core.database.models import StagingEntry, DataEntry, ProcessingStatus
from core.content.images import compress_image, generate_thumbnail, extract_distinct_colors, generate_img_b64_list
from core.ai.ai import call_llm_api, call_vec_api

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=4)

def encode_image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def process_entry_async(staging_entry_id):
    executor.submit(_process_entry, staging_entry_id)

def _process_entry(entry_id):
    session = get_db_session()
    try:
        staging_entry = session.query(StagingEntry).get(entry_id)
        if not staging_entry:
            return
        
        source_type = staging_entry.source_type
        original_path = staging_entry.file_path
        user_id = staging_entry.user_id

        staging_entry.status = ProcessingStatus.PROCESSING
        session.commit()

        file_name = os.path.basename(original_path)
        final_filepath = os.path.join(Config.UPLOAD_DIR, file_name)
        logger.info(f"original_path: {original_path}\nfile_name: {file_name}\nfinal_filepath: {final_filepath}\n")

        # General case: copy file to upload directory
        if os.path.abspath(original_path) != os.path.abspath(final_filepath):
            shutil.copy(original_path, final_filepath)
            logger.info(f"Copied file to upload dir: {final_filepath}")
        else:
            logger.info("Source and destination paths are the same; skipping copy.")

        if source_type in ['image', 'imageurl']:
            with open(final_filepath, "rb") as f:
                new_filepath = compress_image(f)
                if not new_filepath:
                    raise Exception("Compression failed; new_filepath is None")

            image_base64 = [encode_image_to_base64(new_filepath)]
            extracted_content = call_llm_api(
                image_list=image_base64
            )
            tags_vector = call_vec_api(
                query_text=extracted_content, 
                task_type="RETRIEVAL_DOCUMENT"
            )
            swatch_vector = extract_distinct_colors(new_filepath)
            thumbnail_path = generate_thumbnail(new_filepath)
            final_filepath = new_filepath

        else:
            raise Exception(f"Unsupported source_type: {source_type}")

        data_entry = DataEntry(
            user_id=user_id,
            file_path=final_filepath,
            thumbnail_path=thumbnail_path,
            tags=extracted_content,
            tags_vector=tags_vector,
            swatch_vector=swatch_vector,
            timestamp=int(time.time())
        )
        session.add(data_entry)

        staging_entry.status = ProcessingStatus.COMPLETED
        session.commit()
        
        l = f"[{source_type}] Entry {entry_id} processed."
        logger.info(l)
    
    except Exception as e:
        e = f"[{source_type}] Entry {entry_id} processing error\n{e}"
        logger.error(e)
        traceback.print_exc()
        
        staging_entry = session.query(StagingEntry).get(entry_id)
        if staging_entry:
            staging_entry.status = ProcessingStatus.FAILED
            session.commit()
    
    finally:
        if staging_entry.file_path and os.path.exists(staging_entry.file_path):
            os.remove(staging_entry.file_path)
        session.close()
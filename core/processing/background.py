# core/processing/background.py

import time, os, shutil, logging, tempfile, threading, base64, traceback
from core.utils.config import Config
from concurrent.futures import ThreadPoolExecutor
from core.browser.browser import screenshot_url
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
        post_url = staging_entry.post_url

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
            tags_list_str = call_llm_api(
                sysprompt=Config.IMAGE_PREPROCESS_SYSTEM_PROMPT, 
                text_or_images=image_base64
            )
            tags_vector = call_vec_api(tags_list_str)
            swatch_vector = extract_distinct_colors(new_filepath)
            thumbnail_path = generate_thumbnail(new_filepath)
            final_filepath = new_filepath
            
        elif source_type == 'pdf':
            image_base64 = generate_img_b64_list(original_path)
            tags_list_str = call_llm_api(
                sysprompt=Config.IMAGE_PREPROCESS_SYSTEM_PROMPT,
                text_or_images=image_base64
            )
            tags_vector = call_vec_api(tags_list_str)
            swatch_vector = None
            thumbnail_path = generate_thumbnail(original_path)
            final_filepath = original_path
        
        elif source_type == 'text':
            with open(original_path, "r") as f:
                selected_text = f.read()
            
            # Processing
            tags_list_str = selected_text
            tags_vector = call_vec_api(selected_text)
            swatch_vector = None
            thumbnail_path = generate_thumbnail(original_path)
            final_filepath = original_path
        
        elif source_type == 'url':
            with open(original_path, "r") as f:
                url = f.read().strip()

            name = os.path.splitext(os.path.basename(original_path))[0]
            screenshot_temp = os.path.join(tempfile.gettempdir(), f"{name}.jpg")

            # Create a thread to run screenshot_url
            screenshot_success = [False]

            def run_screenshot():
                screenshot_success[0] = screenshot_url(url, path=screenshot_temp)

            t = threading.Thread(target=run_screenshot)
            t.start()
            t.join()

            if not screenshot_success[0] or not os.path.exists(screenshot_temp):
                raise FileNotFoundError(f"Screenshot failed or file not found: {screenshot_temp}")

            with open(screenshot_temp, "rb") as f:
                final_filepath = compress_image(f)

            image_base64 = [encode_image_to_base64(final_filepath)]
            tags_list_str = call_llm_api(
                sysprompt=Config.IMAGE_PREPROCESS_SYSTEM_PROMPT, 
                text_or_images=image_base64
            )
            tags_vector = call_vec_api(tags_list_str)
            swatch_vector = extract_distinct_colors(final_filepath)
            thumbnail_path = generate_thumbnail(final_filepath)

        else:
            raise Exception(f"Unsupported source_type: {source_type}")

        data_entry = DataEntry(
            user_id=user_id,
            file_path=final_filepath,
            thumbnail_path=thumbnail_path,
            post_url=post_url,
            tags=tags_list_str,
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
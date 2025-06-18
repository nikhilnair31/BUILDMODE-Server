# file_management.py

import os, time, uuid, zipfile, json, logging, tempfile, requests, traceback

from io import BytesIO
from routes import file_management_bp
from werkzeug.utils import secure_filename
from flask import request, jsonify, send_file, send_from_directory, abort

from core.utils.cache import clear_user_cache
from core.database.database import get_db_session
from core.database.models import StagingEntry, DataEntry, User, ProcessingStatus
from core.utils.middleware import limiter
from core.utils.logs import error_response
from core.utils.decoraters import token_required, save_limit_required
from core.utils.config import Config
from core.processing.background import process_entry_async

logger = logging.getLogger(__name__)

@file_management_bp.route('/upload/image', methods=['POST'])
@token_required
@save_limit_required
def upload_image(current_user):
    logger.info("\nReceived request to upload image\n")
    try:
        # Check if user exists
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # Check if content exists
        file = request.files.get('image')
        if not file:
            logger.error("No image file provided.")
            return error_response("No image file provided.", 400)
        logger.info(f"Received filename: {file.filename}")

        # Save file to temp
        file_uuid_token = uuid.uuid4().hex
        original_filename = secure_filename(file.filename)
        original_ext = os.path.splitext(original_filename)[1]
        temp_filename = f"{file_uuid_token}{original_ext}"
        temp_path = os.path.join(tempfile.gettempdir(), temp_filename)
        file.save(temp_path)

        # Save initial info with PENDING status
        entry = StagingEntry(
            user_id=user.id,
            file_path=temp_path,
            post_url="-",
            timestamp=int(time.time()),
            source_type='image',
            status=ProcessingStatus.PENDING
        )
        session.add(entry)
        session.commit()
        logger.info(f"StagingEntry {entry.id} created with PENDING status.")
        
        # Kick off async processing
        process_entry_async(entry.id)

        # Clearing cache
        clear_user_cache(current_user.id)

        return jsonify({
            'status': 'success',
            'message': 'Image upload accepted and is being processed',
            'entry_id': entry.id
        }), 200
    
    except Exception as e:
        e = f"Error processing image upload: {e}"
        logger.error(e)
        traceback.print_exc()
        if session:
            session.rollback()
        return error_response(e, 500)
    
    finally:
        if session:
            session.close()

@file_management_bp.route('/upload/imageurl', methods=['POST'])
@token_required
@save_limit_required
def upload_imageurl(current_user):
    logger.info("\nReceived request to upload image from URL\n")
    try:
        # Check if user exists
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # Check if content exists
        image_url = request.form.get("image_url")
        post_url = request.form.get("post_url", "-")
        if not image_url:
            e = f"No image URL provided."
            logger.error(e)
            return error_response(e, 400)
        logger.info(f"Received image URL: {image_url[:10]}")
        
        # Fetch image
        response = requests.get(image_url, stream=True)
        logger.info(f"response: {response}")
        if response.status_code != 200:
            raise Exception(f"Failed to fetch image from URL: {image_url}")

        # Save file to temp
        file_uuid_token = uuid.uuid4().hex
        temp_filename = secure_filename(f"{file_uuid_token}.jpg")
        temp_path = os.path.join(tempfile.gettempdir(), temp_filename)
        with open(temp_path, "wb") as out_file:
            out_file.write(response.content)
        
        # Save initial info with PENDING status
        entry = StagingEntry(
            user_id=user.id,
            file_path=temp_path,
            post_url=post_url,
            timestamp=int(time.time()),
            source_type='image',
            status=ProcessingStatus.PENDING
        )
        session.add(entry)
        session.commit()
        logger.info(f"StagingEntry {entry.id} created with PENDING status.")
        
        # Kick off async processing
        process_entry_async(entry.id)

        # Clearing cache
        clear_user_cache(current_user.id)

        return jsonify({
            'status': 'success',
            'message': 'Image URL accepted and is being processed',
            'entry_id': entry.id
        }), 200
    
    except Exception as e:
        e = f"Error processing image URL upload: {e}"
        logger.error(e)
        traceback.print_exc()
        if session:
            session.rollback()
        return error_response(e, 500)
    
    finally:
        if session:
            session.close()

@file_management_bp.route('/upload/pdf', methods=['POST'])
@token_required
@save_limit_required
def upload_pdf(current_user):
    logger.info("\nReceived request to upload PDF\n")
    try:
        # Check if user exists
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # Check if content exists
        file = request.files.get("pdf")
        if not file:
            e = "No PDF file uploaded"
            logger.error(e)
            return error_response(e, 400)
        logger.info(f"Received filename: {file.filename}")

        # Save file to temp
        file_uuid_token = uuid.uuid4().hex
        original_filename = secure_filename(file.filename)
        original_ext = os.path.splitext(original_filename)[1]
        temp_filename = f"{file_uuid_token}{original_ext}"
        temp_path = os.path.join(Config.UPLOAD_DIR, temp_filename)
        file.save(temp_path)

        # Save initial info with PENDING status
        entry = StagingEntry(
            user_id=user.id,
            file_path=temp_path,
            post_url="-",
            timestamp=int(time.time()),
            source_type='pdf',
            status=ProcessingStatus.PENDING
        )
        session.add(entry)
        session.commit()
        logger.info(f"StagingEntry {entry.id} created with PENDING status.")

        # Kick off async processing
        process_entry_async(entry.id)

        # Clearing cache
        clear_user_cache(current_user.id)

        return jsonify({
            'status': 'success',
            'message': 'PDF accepted and is being processed',
            'entry_id': entry.id
        }), 200

    except Exception as e:
        e = f"Error processing PDF upload: {e}"
        logger.error(e)
        traceback.print_exc()
        if session:
            session.rollback()
        return error_response(e, 500)
    
    finally:
        if session:
            session.close()

@file_management_bp.route('/upload/text', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_text(current_user):
    logger.info("\nReceived request to upload text\n")
    try:
        # Check if user exists
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # Check if content exists
        selected_text = request.form['text']
        if not selected_text:
            e = f"No text provided."
            logger.error(e)
            return error_response(e, 400)
        logger.info(f"Received text: {selected_text[:10]}")
        
        # Save file to temp
        file_uuid_token = uuid.uuid4().hex
        temp_filename = secure_filename(f"{file_uuid_token}.txt")
        temp_path = os.path.join(Config.UPLOAD_DIR, temp_filename)
        with open(temp_path, "w", encoding="utf-8") as out_file:
            out_file.write(selected_text)
        
        # Save initial info with PENDING status
        entry = StagingEntry(
            user_id=user.id,
            file_path=temp_path,
            post_url="-",
            timestamp=int(time.time()),
            source_type='text',
            status=ProcessingStatus.PENDING
        )
        session.add(entry)
        session.commit()
        logger.info(f"StagingEntry {entry.id} created with PENDING status.")

        # Kick off async processing
        process_entry_async(entry.id)

        # Clearing cache
        clear_user_cache(current_user.id)

        return jsonify({
            'status': 'success',
            'message': 'Text accepted and is being processed',
            'entry_id': entry.id
        }), 200

    except Exception as e:
        e = f"Error processing text upload: {e}"
        logger.error(e)
        traceback.print_exc()
        if session:
            session.rollback()
        return error_response(e, 500)
    
    finally:
        if session:
            session.close()

@file_management_bp.route('/upload/url', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_url(current_user):
    logger.info("\nReceived request to upload URL\n")
    try:
        # Check if user exists
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # Check if content exists
        url = request.form['url']
        if not url:
            logger.error("No URL provided.")
            return error_response("No URL provided.", 400)
        logger.info(f"Received URL: {url[:10]}")
        
        # Save file to temp
        file_uuid_token = uuid.uuid4().hex
        temp_filename = secure_filename(f"{file_uuid_token}.txt")
        temp_path = os.path.join(tempfile.gettempdir(), temp_filename)
        with open(temp_path, "w", encoding="utf-8") as out_file:
            out_file.write(url)
        
        # Save initial info with PENDING status
        entry = StagingEntry(
            user_id=user.id,
            file_path=temp_path,
            post_url="-",
            timestamp=int(time.time()),
            source_type='url',
            status=ProcessingStatus.PENDING
        )
        session.add(entry)
        session.commit()
        logger.info(f"StagingEntry {entry.id} created with PENDING status.")

        # Kick off async processing
        process_entry_async(entry.id)

        # Clearing cache
        clear_user_cache(current_user.id)

        return jsonify({
            'status': 'success',
            'message': 'URL accepted and is being processed',
            'entry_id': entry.id
        }), 200

    except Exception as e:
        e = f"Error processing URL upload: {e}"
        logger.error(e)
        traceback.print_exc()
        if session:
            session.rollback()
        return error_response(e, 500)
    
    finally:
        if session:
            session.close()

@file_management_bp.route('/upload/html', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_html(current_user):
    logger.info("\nReceived request to index site\n")
    try:
        # Check if user exists
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # Check fields
        html_file = request.files.get('html')
        html_content = html_file.read().decode("utf-8")
        url = request.form.get('url')
        timestamp_raw = request.form.get('timestamp')
        try:
            timestamp = int(int(timestamp_raw) / 1000)
        except:
            timestamp = int(time.time())
        if not html_file or not url:
            return error_response("Missing required fields: html or url", 400)

        # Call LLM to extract post URLs
        from core.ai.ai import call_llm_api  # inline to ensure context
        post_urls_str = call_llm_api(
            sysprompt=Config.HTML_POST_EXTRACTION_SYSTEM_PROMPT,
            text_or_images=html_content
        )
        logger.info(f"LLM extracted: {post_urls_str[:20]}...")

        # Try parsing list
        try:
            parsed = json.loads(post_urls_str)
            post_urls = parsed.get("urls", [])
            logger.info(f"len post_urls\n{len(post_urls)}")
            logger.info(f"post_urls\n{post_urls[:2]}")
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return error_response("LLM response invalid or malformed", 500)

        if not isinstance(post_urls, list):
            logger.error("LLM response is not a list.")
            return error_response("LLM response must be a JSON list of URLs", 500)

        # Create StagingEntries for each URL
        staging_entries = []
        for post_url in post_urls:
            logger.info(f"post_url\n{post_url}")
            if not isinstance(post_url, str) or not post_url.startswith("http"):
                continue
            
            # Save file to temp
            file_uuid_token = uuid.uuid4().hex
            temp_filename = secure_filename(f"{file_uuid_token}.txt")
            temp_path = os.path.join(tempfile.gettempdir(), temp_filename)
            with open(temp_path, "w", encoding="utf-8") as out_file:
                out_file.write(post_url)

            entry = StagingEntry(
                user_id=user.id,
                file_path=temp_path,
                post_url="-",
                timestamp=int(timestamp),
                source_type='url',
                status=ProcessingStatus.PENDING
            )
            session.add(entry)
            staging_entries.append(entry)

        session.commit()

        # Trigger processing
        logger.info(f"len staging_entries\n{len(staging_entries)}")
        for entry in staging_entries:
            logger.info(f"entry.id\n{entry.id}")
            process_entry_async(entry.id)

        clear_user_cache(current_user.id)

        return jsonify({
            'status': 'success',
            'message': f'Extracted and queued {len(staging_entries)} URLs',
            'count': len(staging_entries),
        }), 200

    except Exception as e:
        e = f"Error processing HTML upload: {e}"
        logger.error(e)
        traceback.print_exc()
        if session:
            session.rollback()
        return error_response(e, 500)
    
    finally:
        if session:
            session.close()

@file_management_bp.route('/delete/file', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
def delete_file(current_user):
    try:
        logger.info("\nReceived request to delete file\n")
        file_name = request.form['file_name']
        if not file_name:
            e = "No file_name provided."
            logger.error(e)
            return error_response(e, 400)
        file_path = os.path.join(Config.UPLOAD_DIR, file_name)
        logger.info(f"Received file_path: {file_path}\n")

        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        entry = session.query(DataEntry).filter_by(file_path=file_path, user_id=user.id).first()
        if not entry:
            e = f"No entry found for file_path: {file_path}"
            logger.error(e)
            return error_response(e, 404)

        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
        else:
            logger.warning(f"File not found at path: {file_path}")

        session.delete(entry)
        session.commit()

        clear_user_cache(current_user.id)
        return jsonify({'status': 'success', 'message': 'Deleted file successfully'})
    
    except Exception as e:
        e = f"Error deleting file: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        session.close()

@file_management_bp.route('/get_file/<filename>')
# @limiter.limit("5 per second;30 per minute")
@token_required
def get_file(current_user, filename):
    session = get_db_session()
    user = session.query(User).get(current_user.id)
    if not user:
        logger.error(f"User {current_user.username} not found.\n")
        return error_response(f"User {current_user.username} not found.", 404)

    filename = secure_filename(filename)
    file_path = os.path.join(Config.UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        abort(404) # Or return error_response("File not found", 404)

    return send_from_directory(Config.UPLOAD_DIR, filename)

@file_management_bp.route('/get_thumbnail/<thumbnailname>')
@limiter.limit("25 per second")
@token_required
def get_thumbnail(current_user, thumbnailname):
    session = get_db_session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)

    thumbnailname = secure_filename(thumbnailname)
    file_path = os.path.join(Config.THUMBNAIL_DIR, thumbnailname)
    if not os.path.exists(file_path):
        abort(404) # Or return error_response("Thumbnail not found", 404)

    return send_from_directory(Config.THUMBNAIL_DIR, thumbnailname)

@file_management_bp.route('/bulk_download_all', methods=['GET'])
# @limiter.limit("1 per second")
@token_required
def bulk_download_all(current_user):
    session = get_db_session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        user_files = session.query(DataEntry).filter(DataEntry.user_id == user.id).all()
        logger.info(f"Found {len(user_files)} files for user {user.username}\n")

        if not user_files:
            return jsonify({"message": "No files found"}), 404

        master_data = []
        for file in user_files:
            master_data.append({
                "id": file.id,
                "file_path": os.path.basename(file.file_path), # Only include base name for security/simplicity
                "post_url": file.post_url,
                "tags": file.tags,
                "timestamp": file.timestamp,
                "user_id": file.user_id
            })

        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            zf.writestr("master.json", json.dumps(master_data, indent=2))

            for file in user_files:
                path = file.file_path
                if os.path.exists(path):
                    arcname = os.path.basename(path)
                    zf.write(path, arcname=f'files/{arcname}') # Put files in a 'files' subfolder

        memory_file.seek(0)
        return send_file(memory_file, download_name="FORGOR_backup.zip", as_attachment=True)
    except Exception as e:
        e = f"Error bulk downloading files: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        session.close()
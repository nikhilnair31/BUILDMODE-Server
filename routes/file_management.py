import os
import base64
import time
import uuid
import zipfile
import json
import logging
import tempfile
import requests
import traceback
from io import BytesIO
from flask import request, jsonify, send_file, send_from_directory, abort
from werkzeug.utils import secure_filename
from routes import file_management_bp
from core.database.database import get_db_session
from core.database.models import DataEntry, User
from core.utils.logs import error_response
from core.utils.decoraters import token_required, save_limit_required
from core.utils.cache import clear_user_cache
from core.utils.config import Config
from core.content.images import extract_distinct_colors, generate_img_b64_list, compress_image, generate_thumbnail
from core.browser.browser import screenshot_url
from core.ai.ai import call_llm_api, call_vec_api

logger = logging.getLogger(__name__)

@file_management_bp.route('/upload/image', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_image(current_user):
    try:
        logger.info("\nReceived request to upload image\n")
        file = request.files.get('image')
        if not file:
            logger.error("No image file provided.")
            return error_response("No image file provided.", 400)
        logger.info(f"Received filename: {file.filename}")

        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        final_filepath = compress_image(file, Config.UPLOAD_DIR)
        thumbnail_path = generate_thumbnail(final_filepath, Config.THUMBNAIL_DIR)

        IMAGE_BASE64 = [base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")]

        content = call_llm_api(
            sysprompt=Config.IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list=IMAGE_BASE64
        )
        embedding = call_vec_api(content)
        swatch_vector = extract_distinct_colors(final_filepath)

        entry = DataEntry(
            file_path=final_filepath, 
            thumbnail_path=thumbnail_path,
            post_url="-",
            tags=content, 
            tags_vector=embedding,
            swatch_vector=swatch_vector,
            timestamp=int(time.time()),
            user_id=user.id,
        )
        session.add(entry)
        session.commit()

        clear_user_cache(current_user.id)
        return jsonify({'status': 'success', 'message': 'Uploaded and processed successfully'}), 200
    
    except Exception as e:
        e = f"Error processing image upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        session.close()

@file_management_bp.route('/upload/imageurl', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_imageurl(current_user):
    try:
        logger.info("\nReceived request to upload image from URL\n")
        image_url = request.form.get("image_url")
        post_url = request.form.get("post_url", "-")

        if not image_url:
            e = f"No image URL provided."
            logger.error(e)
            return error_response(e, 400)

        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        logger.info(f"Downloading image from: {image_url[:25]}")
        response = requests.get(image_url, stream=True)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch image from URL: {image_url}")

        url_ext = os.path.splitext(image_url)[1]
        if url_ext.lower() not in [".png", ".jpg", ".jpeg", ".webp"]:
            raise Exception(f"Unsupported image format: {url_ext}. Only PNG, JPG, JPEG, and WEBP are allowed.")
        
        file_uuid_token = uuid.uuid4().hex
        temp_filename = secure_filename(f"{file_uuid_token}.jpg")
        temp_path = os.path.join(tempfile.gettempdir(), temp_filename)
        with open(temp_path, "wb") as out_file:
            out_file.write(response.content)

        with open(temp_path, "rb") as f:
            final_filepath = compress_image(f, Config.UPLOAD_DIR)
        
        thumbnail_rel_path = generate_thumbnail(final_filepath, Config.THUMBNAIL_DIR)
        IMAGE_BASE64 = [base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")]

        content = call_llm_api(
            sysprompt=Config.IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list=IMAGE_BASE64
        )
        embedding = call_vec_api(content)
        swatch_vector = extract_distinct_colors(final_filepath)

        entry = DataEntry(
            file_path=final_filepath, 
            thumbnail_path=thumbnail_rel_path,
            post_url=post_url,
            tags=content, 
            tags_vector=embedding,
            swatch_vector=swatch_vector,
            timestamp=int(time.time()),
            user_id=user.id,
        )
        session.add(entry)
        session.commit()

        clear_user_cache(current_user.id)
        return jsonify({'status': 'success', 'message': 'Image from URL processed successfully'}), 200
    
    except Exception as e:
        e = f"Error processing image URL upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        session.close()

@file_management_bp.route('/upload/text', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_text(current_user):
    logger.info("\nReceived request to upload text\n")
    try:
        selected_text = request.form['text']
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        logger.info(f"Received from {user.username} a text: {selected_text}\n")
        
        file_uuid_token = uuid.uuid4().hex
        final_filename = secure_filename(f"{file_uuid_token}.txt")
        final_filepath = os.path.join(Config.UPLOAD_DIR, final_filename)
        with open(final_filepath, "w") as f:
            f.write(selected_text)
        logger.info(f"Saved text to: {final_filepath}\n")
    
        thumbnail_rel_path = generate_thumbnail(final_filepath, Config.THUMBNAIL_DIR)
        embedding = call_vec_api(selected_text)

        entry = DataEntry(
            file_path=final_filepath, 
            thumbnail_path=thumbnail_rel_path,
            post_url="-",
            tags=selected_text, 
            tags_vector=embedding,
            swatch_vector=None,
            timestamp=int(time.time()),
            user_id=user.id,
        )
        session.add(entry)
        session.commit()

        clear_user_cache(current_user.id)
        return jsonify({'status': 'success', 'message': 'Text processed successfully'}), 200

    except Exception as e:
        e = f"Error processing text upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        session.close()

@file_management_bp.route('/upload/url', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_url(current_user):
    try:
        url = request.form['url']
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        logger.info(f"Received from {user.username} a url: {url[:25]}\n")
        
        file_uuid_token = uuid.uuid4().hex
        temp_filename = secure_filename(f"{file_uuid_token}.jpg")
        temp_path = os.path.join(tempfile.gettempdir(), temp_filename)
        screenshot_url(url, path=temp_path, wait_seconds=2, headless=True)
        
        with open(temp_path, "rb") as f:
            final_filepath = compress_image(f, Config.UPLOAD_DIR)
    
        thumbnail_rel_path = generate_thumbnail(final_filepath, Config.THUMBNAIL_DIR)
        IMAGE_BASE64 = [base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")]

        content = call_llm_api(
            sysprompt=Config.IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list=IMAGE_BASE64
        )
        embedding = call_vec_api(content)
        swatch_vector = extract_distinct_colors(final_filepath)

        entry = DataEntry(
            file_path=final_filepath, 
            thumbnail_path=thumbnail_rel_path,
            post_url=url,
            tags=content, 
            tags_vector=embedding,
            swatch_vector=swatch_vector,
            timestamp=int(time.time()),
            user_id=user.id,
        )
        session.add(entry)
        session.commit()

        clear_user_cache(current_user.id)
        return jsonify({'status': 'success', 'message': 'URL processed successfully'}), 200
    
    except Exception as e:
        e = f"Error processing text upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        session.close()

@file_management_bp.route('/upload/pdf', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_pdf(current_user):
    file = request.files.get("pdf")
    if not file:
        e = "No PDF file uploaded"
        logger.error(e)
        return error_response(e, 400)

    try:
        timestamped_filename = f"{file.filename}_{int(time.time())}.pdf"
        save_path = os.path.join(Config.UPLOAD_DIR, timestamped_filename)
        file.save(save_path)
        
        thumbnail_rel_path = generate_thumbnail(save_path, Config.THUMBNAIL_DIR)
        image_b64_list = generate_img_b64_list(save_path)
        if not image_b64_list:
            e = "No pages found in PDF"
            logger.error(e)
            return error_response(e, 400)

        content = call_llm_api(
            sysprompt=Config.IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list=image_b64_list
        )
        embedding = call_vec_api(content)

        session = get_db_session()
        entry = DataEntry(
            file_path=save_path,
            thumbnail_path=thumbnail_rel_path,
            post_url="-",
            tags=content,
            tags_vector=embedding,
            swatch_vector=None,
            timestamp=int(time.time()),
            user_id=current_user.id,
        )
        session.add(entry)
        session.commit()

        clear_user_cache(current_user.id)
        return jsonify({"status": "success", "message": "PDF uploaded and processed"})

    except Exception as e:
        e = f"Error processing PDF upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
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
# @limiter.limit("5 per second;30 per minute")
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
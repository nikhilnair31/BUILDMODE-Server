# data.py

import os, time, uuid, zipfile, json, logging, tempfile, requests, traceback

from io import BytesIO
from routes import data_bp
from werkzeug.utils import secure_filename
from flask import request, jsonify, url_for, send_file, send_from_directory, abort

from core.utils.cache import clear_user_cache
from core.database.database import get_db_session
from core.database.models import StagingEntry, DataEntry, User, ProcessingStatus
from core.utils.middleware import limiter
from core.utils.logs import error_response
from core.utils.decoraters import token_required, save_limit_required
from core.utils.config import Config
from core.processing.background import process_entry_async
from core.notifications.emails import send_email_with_zip

logger = logging.getLogger(__name__)

# ---------------------------------- UPLOADING ------------------------------------

@data_bp.route('/upload/image', methods=['POST'])
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

@data_bp.route('/upload/imageurl', methods=['POST'])
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

# ---------------------------------- DELETING ------------------------------------

@data_bp.route('/delete/file', methods=['POST'])
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

# ---------------------------------- GETTING ------------------------------------

@data_bp.route('/get_file/<filename>')
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

@data_bp.route('/get_thumbnail/<thumbnailname>')
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

# ---------------------------------- DOWNLOADING ------------------------------------

@data_bp.route('/bulk_download_all', methods=['GET'])
@limiter.limit("1 per second")
@token_required
def bulk_download_all(current_user):
    logger.info(f"\nBulk download for: {current_user.id}\n")
    
    session = get_db_session()
    
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        if not user.email or "@" not in str(user.email):
            logger.error(f"User {user.id} has no valid email: {user.email!r}")
            return error_response("No valid email on file for this account.", 400)
        
        user_files = session.query(DataEntry).filter(DataEntry.user_id == user.id).all()
        logger.info(f"Found {len(user_files)} files for user {user.username}\n")

        if not user_files:
            return jsonify({"message": "No files found"}), 404

        master_data = []
        for file in user_files:
            master_data.append({
                "id": file.id,
                "thumbnail_path": os.path.basename(file.thumbnail_path), # Only include base name for security/simplicity
                "tags": file.tags,
                "timestamp": file.timestamp,
                "user_id": file.user_id
            })

        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            zf.writestr("master.json", json.dumps(master_data, indent=2))

            for file in user_files:
                path = file.thumbnail_path
                if os.path.exists(path):
                    arcname = os.path.basename(path)
                    zf.write(path, arcname=f'files/{arcname}') # Put files in a 'files' subfolder

        memory_file.seek(0)
        zip_bytes = memory_file.getvalue()
        zip_size_bytes = len(zip_bytes)
        logger.info(f"ZIP size: {zip_size_bytes} bytes ({zip_size_bytes/1024:.2f} KB)")

        # Send as email attachment
        sent = send_email_with_zip(
            user_email=user.email,
            subject="Your FORGOR Backup",
            body="Attached is your full FORGOR backup as requested.",
            zip_bytes=memory_file
        )

        if sent:
            return jsonify({"message": "Backup sent to your email."}), 200
        else:
            return error_response("Failed to send backup email", 500)
    
    except Exception as e:
        logger.error("Bulk download failed")
        return error_response(f"Error bulk downloading files: {e}", 500)
    
    finally:
        session.close()
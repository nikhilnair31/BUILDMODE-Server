# app.py

# region Imports
import os
import jwt
import json
import time
import uuid
import base64
import zipfile
import logging
import tempfile
import datetime
import warnings
import traceback
import requests
from io import BytesIO
from hashlib import sha256
from cachetools import TTLCache
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text, create_engine
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from image import (
    extract_distinct_colors,
    generate_img_b64_list
)
from browser import (
    screenshot_url
)
from pre_process import (
    compress_image,
    generate_thumbnail
)
from parser import (
    parse_url_or_text,
    parse_time_input,
    extract_color_code,
    timezone_to_start_of_day_ts,
    clean_text_of_color_and_time,
    rgb_to_vec
)
from ai import (
    call_llm_api,
    call_vec_api
)
from models import (
    Base,
    DataEntry,
    User,
    Tier
)
from functools import (
    wraps, 
    lru_cache
)
from flask import (
    Flask, 
    request, 
    jsonify,
    abort,
    send_file,
    send_from_directory
)
# endregion

#region Config & Constants
load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)

class Config:
    APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    MIA_DB_NAME = os.getenv("MIA_DB_NAME")
    MIA_DB_PASSWORD = os.getenv("MIA_DB_PASSWORD")
    THUMBNAIL_DIR = os.getenv("THUMBNAIL_DIR")
    UPLOAD_DIR = os.getenv("UPLOAD_DIR")

ALLOWED_USER_AGENTS = [
    "YourAndroidApp/1.0",     # Replace with your app’s user-agent
    "python-requests",        # Allow during dev/testing
    "PostmanRuntime",         # Optional: for Postman testing
]

IMAGE_PREPROCESS_SYSTEM_PROMPT = """
    Extract a long and comprehensive list of keywords to describe the image provided. These keywords will be used for semantic search eventually. Extract things like themes, dominant/accent colors, moods along with more descriptive terms. If possible determine the app the screenshot was taken in as well. Ignore phone status information. Only output as shown below
    <tags>
    keyword1, keyword2, ...
    </tags>
"""

ENGINE_URL = f'postgresql://postgres:{Config.MIA_DB_PASSWORD}@localhost/{Config.MIA_DB_NAME}'
# endregion

# region Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"Connecting to database at: {ENGINE_URL}")

def error_response(message, status_code=400, status='error', extra=None):
    payload = {
        'status': status,
        'message': message
    }
    if extra:
        payload.update(extra)
    return jsonify(payload), status_code
# endregion

# region Flask App Initialization
app = Flask(__name__)
app.config.from_object(Config)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Rate Limiting
limiter = Limiter(
    get_remote_address, 
    app=app, 
    default_limits=["100 per day", "30 per hour"]
)

# Allow all origins for now, or restrict to your frontend domain
CORS(app, supports_credentials=True, resources={
    r"/api/*": {
        "origins": [
            "https://forgor.space",        # Covers https://forgor.space/app
        ]
    }
})
# endregion

# region Database Initialization
engine = create_engine(ENGINE_URL)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)
# endregion

#region Helpers
def get_ip():
    # logger.info(f"request.headers: {dict(request.headers)}\n")
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    ip = forwarded_for.split(',')[0] if forwarded_for else request.headers.get('X-Real-IP', request.remote_addr)
    logger.info(f"Detected IP: {ip}")
    return ip
def get_user_upload_info(current_user):
    logger.info(f"Getting upload info for user: {current_user.username}\n")
    session = Session()
    try:
        tier = session.query(Tier).get(current_user.tier_id)
        if not tier:
            return None, jsonify({'message': 'Invalid user tier'}), 403, session
        
        start_of_day_ts = timezone_to_start_of_day_ts(current_user.timezone)
        uploads_today = session.query(DataEntry).filter(
            DataEntry.user_id == current_user.id,
            DataEntry.timestamp >= start_of_day_ts
        ).count()
        uploads_left = max(0, tier.daily_limit - uploads_today)
        reset_in_seconds = int((start_of_day_ts + 86400) - time.time())

        output = {
            'tier_name': tier.name,
            'daily_limit': tier.daily_limit,
            'uploads_today': uploads_today,
            'uploads_left': uploads_left,
            'reset_in_seconds': reset_in_seconds,
            'start_of_day_ts': start_of_day_ts,
        }
        # logger.info(f"output: {output}\n")
        
        return output, None, None, session
    except Exception as e:
        session.close()
        raise e
# endregion

#region Wrappers
def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            e = "Token is missing or invalid"
            logger.error(e)
            return error_response(e, 401)
        
        try:
            data = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
            # logger.info(f"Decoded token payload: {data}")
        except jwt.ExpiredSignatureError:
            e = "Token has expired"
            logger.error(e)
            return error_response(e, 401)
        except jwt.InvalidTokenError:
            e = "Invalid token"
            logger.error(e)
            return error_response(e, 401)
        except Exception as e:
            e = f"Error decoding token: {e}"
            logger.error(e)
            return error_response(e, 500)

        session = Session()
        try:
            user = session.query(User).filter_by(id=data['user_id']).first()
            # logger.info(f"user: {user}")
            if not user:
                e = f"User ID {data['user_id']} not found"
                logger.error(e)
                return error_response(e, 401)
        finally:
            session.close()

        return f(user, *args, **kwargs)
    return wrapper
def save_limit_required(f):
    @wraps(f)
    def wrapper(current_user, *args, **kwargs):
        info, error, status_code, session = get_user_upload_info(current_user)
        if error:
            session.close()
            return error, status_code
        
        try:
            if info['uploads_left'] <= 0:
                e = f"Daily upload limit reached for user {current_user.username} | ({info['tier_name']} - {info['daily_limit']} per day)."
                logger.warning(e)
                return error_response(e, 403)
            return f(current_user, *args, **kwargs)
        finally:
            session.close()
    return wrapper
# endregion

#region Caching
query_cache = TTLCache(maxsize=1000, ttl=300)

def get_cache_key(user_id, query_text):
    return sha256(f"{user_id}:{query_text}".encode()).hexdigest()
def clear_user_cache(user_id):
    keys_to_remove = [k for k in query_cache.keys() if k.startswith(f"{user_id}:")]
    for k in keys_to_remove:
        del query_cache[k]

@lru_cache(maxsize=512)
def cached_call_vec_api(text):
    return call_vec_api(text)
# endregion

#region Before Request
@app.before_request
def restrict_headers():
    if request.path.startswith("/api/get_file/"):
        return
    
    user_agent = request.headers.get("User-Agent", "")
    api_key = request.headers.get("X-App-Key", None)
    # logger.info(f"User-Agent: {user_agent}, API key: {api_key}")

    # Allow during development
    if "python" in user_agent.lower() or "postman" in user_agent.lower():
        return

    # Require custom header
    if not api_key or api_key != Config.APP_SECRET_KEY:
        print(f"Rejected request with UA: {user_agent}, API key: {api_key}")
        abort(403, description="Forbidden: Invalid or missing headers.")
# endregion

#region Endpoints
@app.route('/api/refresh_token', methods=['POST'])
@limiter.limit("2 per second")
def refresh_token():
    data = request.get_json()
    refresh_token = data.get('refresh_token', '')

    try:
        payload = jwt.decode(refresh_token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        e = "Refresh token has expired"
        logger.error(e)
        return error_response(e, 401)
    except jwt.InvalidTokenError:
        e = "Invalid refresh token"
        logger.error(e)
        return error_response(e, 401)

    session = Session()
    user = session.query(User).get(payload['user_id'])
    if not user:
        e = f"User ID {payload['user_id']} not found"
        logger.error(e)
        return error_response(e, 404)

    # Issue new access token
    new_access_token = jwt.encode(
        {
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        },
        Config.JWT_SECRET_KEY,
        algorithm='HS256'
    )

    return jsonify({'access_token': new_access_token}), 200

@app.route('/api/register', methods=['POST'])
@limiter.limit("1 per second")
def register():
    data = request.get_json()
    # logger.info(f"Received registration data: {data}\n")

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    timezone = data.get('timezone', '').strip()
    
    session = Session()
    if session.query(User).filter_by(username=username).first():
        logger.error(f"User {username} already exists.\n")
        return error_response("Username already exists", 400)

    new_user = User(
        username=username,
        timezone=timezone,
        created_at=int(time.time()),
        updated_at=int(time.time())
    )
    new_user.set_password(password)

    session.add(new_user)
    session.commit()

    return jsonify({"status": "success", "message": "User registered successfully."}), 200

@app.route('/api/login', methods=['POST'])
@limiter.limit("1 per second")
def login():
    data = request.get_json()

    session = Session()
    user = session.query(User).filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        logger.error(f"Invalid credentials for user {data['username']}.\n")
        return error_response("Invalid credentials", 401)
    logger.info(f"User {user.username} logged in successfully.\n")

    access_token = jwt.encode(
        {
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, 
        Config.JWT_SECRET_KEY, 
        algorithm='HS256'
    )
    refresh_token = jwt.encode(
        {
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, 
        Config.JWT_SECRET_KEY, 
        algorithm='HS256'
    )
    logger.info(f"Generated access and refresh token\n")
    
    return jsonify(
        {
            'access_token': access_token, 
            'refresh_token': refresh_token
        }
    ), 200

@app.route('/api/update-username', methods=['POST'])
@limiter.limit("1 per second")
@token_required
def update_username(current_user):
    data = request.get_json()

    session = Session()
    try:
        if session.query(User).filter_by(username=data['new_username']).first():
            return error_response("Username already taken", 400)

        # Re-attach or re-fetch user in this session
        user = session.query(User).get(current_user.id)
        user.username = data['new_username']
        session.commit()
    finally:
        session.close()
    
    return jsonify({'message': 'Username updated'}), 200

@app.route('/api/get_saves_left', methods=['GET'])
@limiter.limit("2 per second")
@token_required
def get_saves_left(current_user):
    info, error_response, status_code, session = get_user_upload_info(current_user)
    if error_response:
        session.close()
        return error_response, status_code

    try:
        return jsonify(info), 200
    finally:
        session.close()

@app.route('/api/upload/image', methods=['POST'])
@limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_image(current_user):
    try:
        logger.info("\nReceived request to upload image\n")

        file = request.files['image']
        if not file:
            logger.error("No image file provided.")
            return error_response("No image file provided.", 400)
        logger.info(f"Recived filename: {file.filename}")

        # Check if the user exists
        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        # Compress and save image
        final_filepath = compress_image(file, app.config['UPLOAD_DIR'])
        thumbnail_path = generate_thumbnail(final_filepath, app.config['THUMBNAIL_DIR'])

        # Convert image to base64
        IMAGE_BASE64 = [base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")]

        # Send to OpenAI for processing
        content = call_llm_api(
            sysprompt = IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list = IMAGE_BASE64
        )

        # Create embedding
        embedding = call_vec_api(content)

        # Extract distinct colors
        swatch_vector = extract_distinct_colors(final_filepath)

        # Save to database
        session = Session()
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

        # Clear cache for this user
        clear_user_cache(current_user.id)

        return jsonify({'status': 'success', 'message': 'Uploaded and processed successfully'})
    
    except Exception as e:
        e = f"Error processing image upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)

@app.route('/api/upload/imageurl', methods=['POST'])
@limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_imageurl(current_user):
    try:
        logger.info("\nReceived request to upload image from URL\n")

        image_url = request.form.get("image_url")
        post_url = request.form.get("post_url", "-")  # original page image came from

        if not image_url:
            e = f"No image URL provided."
            logger.error(e)
            return error_response(e, 400)

        session = Session()
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

        processed_path = compress_image(temp_path, app.config['UPLOAD_DIR'])
        final_filename = secure_filename(f"{file_uuid_token}.jpg")
        final_filepath = os.path.join(app.config['UPLOAD_DIR'], final_filename)
        os.rename(processed_path, final_filepath)
        
        # Generate and save thumbnail
        thumbnail_uuid_token = uuid.uuid4().hex
        thumbnail_rel_path = generate_thumbnail(final_filepath, thumbnail_uuid_token)

        IMAGE_BASE64 = [base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")]

        content = call_llm_api(
            sysprompt = IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list = IMAGE_BASE64
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

        # Clear cache for this user
        clear_user_cache(current_user.id)

        return jsonify({'status': 'success', 'message': 'Image from URL processed successfully'})
    
    except Exception as e:
        e = f"Error processing image URL upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)

@app.route('/api/upload/text', methods=['POST'])
@limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_text(current_user):
    logger.info("\nReceived request to upload text\n")

    try:
        selected_text = request.form['text']

        # Check if the user exists
        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        logger.info(f"Received from {user.username} a text: {selected_text}\n")
        
        # Final filename and move
        file_uuid_token = uuid.uuid4().hex
        final_filename = secure_filename(f"{file_uuid_token}.txt")
        final_filepath = os.path.join(app.config['UPLOAD_DIR'], final_filename)
        with open(final_filepath, "w") as f:
            f.write(selected_text)
        logger.info(f"Saved text to: {final_filepath}\n")
    
        # Generate and save thumbnail
        thumbnail_uuid_token = uuid.uuid4().hex
        thumbnail_rel_path = generate_thumbnail(final_filepath, thumbnail_uuid_token)

        # Create embedding
        embedding = call_vec_api(selected_text)

        # Save to database
        session = Session()
        entry = DataEntry(
            file_path=final_filepath, 
            thumbnail_path=thumbnail_rel_path,
            post_url="-",
            tags=selected_text, 
            tags_vector=embedding,
            swatch_vector=None,  # No color swatch for text
            timestamp=int(time.time()),
            user_id=user.id,
        )
        session.add(entry)
        session.commit()

        # Clear cache for this user
        clear_user_cache(current_user.id)

        return jsonify({'status': 'success', 'message': 'Text processed successfully'})

    except Exception as e:
        e = f"Error processing text upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)

@app.route('/api/upload/url', methods=['POST'])
@limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_url(current_user):
    logger.info("\nReceived request to upload URL\n")

    try:
        url = request.form['url']

        # Check if the user exists
        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        logger.info(f"Received from {user.username} a url: {url}\n")
        
        # Take screenshot
        file_uuid_token = uuid.uuid4().hex
        temp_filename = secure_filename(f"{file_uuid_token}.jpg")
        temp_path = os.path.join(tempfile.gettempdir(), temp_filename)

        logger.info(f"Taking screenshot of {url}...")
        screenshot_url(url, path=temp_path)
        
        # Downscale and save final image
        processed_path = compress_image(open(temp_path, "rb"), app.config['UPLOAD_DIR'])

        # Final filename and move
        final_filename = secure_filename(f"{file_uuid_token}.jpg")
        final_filepath = os.path.join(app.config['UPLOAD_DIR'], final_filename)
        os.rename(processed_path, final_filepath)
        logger.info(f"Saved processed image to: {final_filepath}\n")
    
        # Generate and save thumbnail
        thumbnail_uuid_token = uuid.uuid4().hex
        thumbnail_rel_path = generate_thumbnail(final_filepath, thumbnail_uuid_token)

        # Convert image to base64
        IMAGE_BASE64 = [base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")]

        # Send to OpenAI for processing
        content = call_llm_api(
            sysprompt = IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list = IMAGE_BASE64
        )

        # Create embedding
        embedding = call_vec_api(content)

        # Extract distinct colors
        swatch_vector = extract_distinct_colors(final_filepath)

        # Save to database
        session = Session()
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

        # Clear cache for this user
        clear_user_cache(current_user.id)

        return jsonify({'status': 'success', 'message': 'URL processed successfully'})
    
    except Exception as e:
        e = f"Error processing text upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)

@app.route('/api/upload/pdf', methods=['POST'])
@limiter.limit("1 per second")
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
        save_path = os.path.join(app.config["UPLOAD_DIR"], timestamped_filename)
        file.save(save_path)
        
        thumbnail_uuid_token = uuid.uuid4().hex
        thumbnail_rel_path = generate_thumbnail(save_path, thumbnail_uuid_token)

        image_b64_list = generate_img_b64_list(save_path)
        if not image_b64_list:
            e = "No pages found in PDF"
            logger.error(e)
            return error_response(e, 400)

        # Send all pages to LLM
        content = call_llm_api(
            sysprompt=IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list=image_b64_list
        )

        # Create embedding
        embedding = call_vec_api(content)

        # Save to DB
        session = Session()
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

        # Clear cache for this user
        clear_user_cache(current_user.id)

        return jsonify({"status": "success", "message": "PDF uploaded and processed"})

    except Exception as e:
        e = f"Error processing PDF upload: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)

@app.route('/api/delete/file', methods=['POST'])
@limiter.limit("1 per second")
@token_required
def delete_file(current_user):
    try:
        logger.info("\nReceived request to delete file\n")

        file_name = request.form['file_name']
        if not file_name:
            e = "No file_name provided."
            logger.error(e)
            return error_response(e, 400)
        file_path = os.path.join(app.config['UPLOAD_DIR'], file_name)
        logger.info(f"Received file_path: {file_path}\n")

        # Check if the user exists
        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # Find entry with this file path and user ID
        entry = session.query(DataEntry).filter_by(file_path=file_path, user_id=user.id).first()
        if not entry:
            e = f"No entry found for file_path: {file_path}"
            logger.error(e)
            return error_response(e, 404)

        # Delete the file if it exists
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
        else:
            logger.warning(f"File not found at path: {file_path}")

        # Delete the database entry
        session.delete(entry)
        session.commit()
        session.close()

        # Clear cache for this user
        clear_user_cache(current_user.id)

        return jsonify({'status': 'success', 'message': 'Deleted file successfully'})
    
    except Exception as e:
        e = f"Error deleting file: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)

@app.route('/api/get_file/<filename>')
@limiter.limit("5 per second;30 per minute")
@token_required
def get_file(current_user, filename):
    # Check if the user exists
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        logger.error(f"User {user.username} not found.\n")
        return jsonify({"status": "error", "message": f"User {user.username} not found."}), 404

    # Sanitize inputs
    filename = secure_filename(filename)

    # Confirm the image exists in that user's folder
    file_path = os.path.join(app.config['UPLOAD_DIR'], filename)
    # logger.info(f"file_path: {file_path}\n")
    if not os.path.exists(file_path):
        abort(404)

    return send_from_directory(app.config['UPLOAD_DIR'], filename)

@app.route('/api/get_thumbnail/<thumbnailname>')
@limiter.limit("5 per second;30 per minute")
@token_required
def get_thumbnail(current_user, thumbnailname):
    # Check if the user exists
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)

    # Sanitize inputs
    thumbnailname = secure_filename(thumbnailname)

    # Confirm the image exists in that user's folder
    file_path = os.path.join(app.config['THUMBNAIL_DIR'], thumbnailname)
    # logger.info(f"file_path: {file_path}\n")
    if not os.path.exists(file_path):
        abort(404)

    return send_from_directory(app.config['THUMBNAIL_DIR'], thumbnailname)

@app.route('/api/get_similar/<filename>')
@limiter.limit("5 per second;30 per minute")
@token_required
def get_similar(current_user, filename):
    session = Session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        # Sanitize and construct path
        filename = secure_filename(filename)
        file_path = os.path.join(app.config['UPLOAD_DIR'], filename)

        # Find the target entry
        entry = session.query(DataEntry).filter_by(file_path=file_path, user_id=user.id).first()
        logger.info(f"entry: {entry} and entry.file_path: {entry.file_path}\n")
        if not entry:
            e = f"No entry found for file_path: {file_path}"
            logger.error(e)
            return error_response(e, 404)
        
        user_id = user.id
        file_path = entry.file_path
        query_vec = entry.tags_vector.tolist()
 
        # Build SQL
        final_sql = f"""
            SELECT file_path, thumbnail_path, post_url, tags_vector <=> '{query_vec}' AS similarity
            FROM data
            WHERE user_id = {user_id} AND file_path != '{file_path}'
            ORDER BY similarity ASC
            LIMIT 100
        """
        results = session.execute(
            text(final_sql)
        ).fetchall()
        logger.info(f"Found {len(results)} similar entries")

        return jsonify({
            "results": [
                {
                    "file_name": os.path.basename(r[0]),
                    "thumbnail_name": os.path.basename(r[1]),
                    "post_url": r[2]
                } for r in results
            ]
        }), 200
    except Exception as e:
        e = f"Error fetching similar content: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        session.close()

@app.route('/api/query', methods=['POST'])
@limiter.limit("5 per second")
@token_required
def query(current_user):
    logger.info(f"\nReceived request to query image from user of id: {current_user.id}\n")

    data = request.json
    logger.info(f"data: {data}\n")

    query_text = data.get("searchText", "").strip()
    if not query_text:
        e = "searchText required"
        logger.error(e)
        return error_response(e, 400)
    
    cache_key = get_cache_key(current_user.id, query_text)
    if cache_key in query_cache:
        logger.info("Serving /api/query from cache.")
        return jsonify(query_cache[cache_key])
    
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)

    userid = user.id
    logger.info(f"Querying for userid: {userid}")
    
    # Extract color
    color_code = extract_color_code(query_text)

    # Extract time and convert to timestamp
    start = time.perf_counter()
    timestamp = parse_time_input(query_text)
    unix_time = int(timestamp.timestamp()) if timestamp else None
    logger.info(f"Query took {(time.perf_counter() - start) * 1000:.2f}ms")

    # Extract content after removing time & color
    cleaned_query = clean_text_of_color_and_time(query_text)
    query_vector = call_vec_api(cleaned_query) if cleaned_query else None

    # Build SELECT fields
    select_fields = ["file_path", "thumbnail_path", "post_url"]
    where_clauses = [f"user_id = '{userid}'"]
    order_by_clauses = []

    # Add color vector filter
    if color_code:
        logger.info("Detected color input")
        swatch_vector = color_code if isinstance(color_code, str) and color_code.startswith("#") else rgb_to_vec(color_code)
        select_fields.append(f"swatch_vector <-> '{swatch_vector}' AS color_distance")
        order_by_clauses.append("color_distance ASC")

    # Add content vector filter
    if query_vector:
        logger.info("Detected content input")
        select_fields.append(f"tags_vector <=> '{query_vector}' AS semantic_distance")
        order_by_clauses.append("semantic_distance ASC")

    # Time filter
    if unix_time:
        logger.info(f"Detected time filter (>= {unix_time})")
        where_clauses.append(f"timestamp >= {unix_time}")
    
    final_sql = f"""
        SELECT {', '.join(select_fields)}
        FROM data
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {', '.join(order_by_clauses) if order_by_clauses else 'timestamp DESC'}
        LIMIT 100
    """

    # Build SQL
    sql = text(final_sql)
    result = session.execute(sql).fetchall()
    logger.info(f"len result: {len(result)}\n")

    result_json = {
        "results": [
            {
                "file_name": f"{os.path.basename(r[0])}",
                "thumbnail_name": f"{os.path.basename(r[1])}",
                "post_url": r[2]
            }
            for r in result
        ]
    }

    # ✅ Save the result in cache
    query_cache[cache_key] = result_json

    return jsonify(result_json)

@app.route('/api/check', methods=['POST'])
@limiter.limit("1 per second")
@token_required
def check(current_user):
    logger.info(f"\nChecking for: {current_user.id}\n")

    data = request.json
    logger.info(f"data: {data}\n")

    query_text = data.get("searchText", "").strip()
    if not query_text:
        e = "searchText required"
        logger.error(e)
        return error_response(e, 400)
    
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)
    
    # Extract color
    color_code = extract_color_code(query_text)

    # Extract time and convert to timestamp
    timestamp = parse_time_input(query_text)
    unix_time = int(timestamp.timestamp()) if timestamp else None

    # Extract content after removing time & color
    cleaned_query = clean_text_of_color_and_time(query_text)
    query_vector = call_vec_api(cleaned_query) if cleaned_query else None

    # Build SELECT fields
    select_fields = ["file_path", "post_url", "tags", "timestamp"]
    where_clauses = [f"user_id = '{user.id}'"]
    order_by_clauses = []

    # Add color vector filter
    if color_code:
        logger.info("Detected color input")
        swatch_vector = color_code if isinstance(color_code, str) and color_code.startswith("#") else rgb_to_vec(color_code)
        select_fields.append(f"swatch_vector <-> '{swatch_vector}' AS color_distance")
        order_by_clauses.append("color_distance ASC")

    # Add content vector filter
    if query_vector:
        logger.info("Detected content input")
        select_fields.append(f"tags_vector <=> '{query_vector}' AS semantic_distance")
        order_by_clauses.append("semantic_distance ASC")

    # Time filter
    if unix_time:
        logger.info(f"Detected time filter (<= {unix_time})")
        where_clauses.append(f"timestamp <= {unix_time}")
    
    final_sql = f"""
        SELECT {', '.join(select_fields)}
        FROM data
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {', '.join(order_by_clauses) if order_by_clauses else 'timestamp DESC'}
        LIMIT 3
    """

    # Build SQL
    sql = text(final_sql)
    result = session.execute(sql).fetchall()
    logger.info(f"result: {result[:1]}\n")

    # Content of value?
    useful_content = len(result) > 0

    return jsonify({
        "results": {
            "useful": useful_content,
            "query": query_text,
        }
    }), 200

@app.route('/api/bulk_download_all', methods=['GET'])
@limiter.limit("1 per second")
@token_required
def bulk_download_all(current_user):
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)

    # Query all data entries for the user
    user_files = session.execute(
        select(DataEntry).where(DataEntry.user_id == user.id)
    ).scalars().all()
    logger.info(f"Found {len(user_files)} files for user {user.username}\n")

    if not user_files:
        return {"message": "No files found"}, 404

    # Prepare JSON metadata
    master_data = []
    for file in user_files:
        master_data.append({
            "id": file.id,
            "file_path": file.file_path,
            "post_url": file.post_url,
            "tags": file.tags,
            "timestamp": file.timestamp,
            "user_id": file.user_id
        })

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        # Write master.json
        zf.writestr("master.json", json.dumps(master_data, indent=2))

        # Add files in subfolder 'files/'
        for file in user_files:
            path = file.file_path
            if os.path.exists(path):
                arcname = os.path.basename(path)
                zf.write(path, arcname=arcname)

    memory_file.seek(0)
    return send_file(memory_file, download_name="FORGOR_backup.zip", as_attachment=True)
# endregion
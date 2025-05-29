import os
import jwt
import time
import uuid
import base64
import logging
import tempfile
import datetime
import warnings
import traceback
import requests
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, create_engine
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
    preprocess_image
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
    send_from_directory
)

#region Initialization
load_dotenv()

warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
MIA_DB_NAME = os.getenv("MIA_DB_NAME")
MIA_DB_PASSWORD = os.getenv("MIA_DB_PASSWORD")

UPLOAD_FOLDER = './uploads'
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
ENGINE_URL = f'postgresql://postgres:{MIA_DB_PASSWORD}@localhost/{MIA_DB_NAME}'
logger.info(f"Connecting to {ENGINE_URL}\n")

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per day", "30 per hour"])
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
engine = create_engine(ENGINE_URL)
Session = sessionmaker(bind=engine)

# Allow all origins for now, or restrict to your frontend domain
CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})

# Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
# endregion

#region Helpers
def get_ip():
    # logger.info(f"request.headers: {dict(request.headers)}\n")
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    ip = forwarded_for.split(',')[0] if forwarded_for else request.headers.get('X-Real-IP', request.remote_addr)
    logger.info(f"Detected IP: {ip}")
    return ip
def get_uploads_today(user_id, start_ts):
    session = Session()
    try:
        return session.query(DataEntry).filter(
            DataEntry.user_id == user_id,
            DataEntry.timestamp >= start_ts
        ).count()
    finally:
        session.close()
# endregion

#region Wrappers
def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        # logger.info(f"Received token: {token}")
        if not token:
            logger.error("Token missing")
            return jsonify({'message': 'Token missing'}), 401
        
        try:
            data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            # logger.info(f"Decoded token payload: {data}")
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401
        except Exception as e:
            logger.error(f"Unexpected error decoding token: {e}")
            return jsonify({'message': 'Token error'}), 500

        session = Session()
        try:
            user = session.query(User).filter_by(id=data['user_id']).first()
            # logger.info(f"user: {user}")
            if not user:
                logger.error(f"User ID {data['user_id']} not found in database.")
                return jsonify({'message': 'User not found'}), 401
        finally:
            session.close()

        return f(user, *args, **kwargs)
    return wrapper
def save_limit_required(f):
    @wraps(f)
    def wrapper(current_user, *args, **kwargs):
        session = Session()
        try:
            tier = session.query(Tier).get(current_user.tier_id)
            if not tier:
                return jsonify({'message': 'Invalid user tier'}), 403
            logger.info(f"User {current_user.username} has tier: {tier.name}\n")
        
            # Get timezone from header (default to UTC)
            start_of_day_ts = timezone_to_start_of_day_ts(current_user.timezone)
            logger.info(f"Start of day timestamp: {start_of_day_ts}\n")

            uploads_today = get_uploads_today(current_user.id, start_of_day_ts)
            logger.info(f"Uploads today for {current_user.username}: {uploads_today}\n")

            if uploads_today >= tier.daily_limit:
                return jsonify({
                    'message': f'Daily upload limit reached ({tier.daily_limit} per day for {tier.name} tier).'
                }), 403
        finally:
            session.close()
        return f(current_user, *args, **kwargs)
    return wrapper
# endregion

#region Caching
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
    if not api_key or api_key != APP_SECRET_KEY:
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
        payload = jwt.decode(refresh_token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'message': 'Refresh token expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'message': 'Invalid refresh token'}), 401

    session = Session()
    user = session.query(User).get(payload['user_id'])
    if not user:
        return jsonify({'message': 'User not found'}), 404

    # Issue new access token
    new_access_token = jwt.encode(
        {
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        },
        JWT_SECRET_KEY,
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
        return jsonify({'message': 'Username already exists'}), 400

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
        return jsonify({'message': 'Invalid credentials'}), 401
    logger.info(f"User {user.username} logged in successfully.\n")

    access_token = jwt.encode(
        {
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, 
        JWT_SECRET_KEY, 
        algorithm='HS256'
    )
    refresh_token = jwt.encode(
        {
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, 
        JWT_SECRET_KEY, 
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
            return jsonify({'message': 'Username already taken'}), 400

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
    session = Session()
    try:
        tier = session.query(Tier).get(current_user.tier_id)
        logger.info(f"User {current_user.username} has tier: {tier.name}\n")
        if not tier:
            return jsonify({'message': 'Invalid user tier'}), 403
        
        # Get timezone from header (default to UTC)
        start_of_day_ts = timezone_to_start_of_day_ts(current_user.timezone)
        logger.info(f"Start of day timestamp: {start_of_day_ts}\n")

        uploads_today = get_uploads_today(current_user.id, start_of_day_ts)
        logger.info(f"Uploads today for {current_user.username}: {uploads_today}\n")

        remaining_uploads = max(0, tier.daily_limit - uploads_today)
        logger.info(f"Remaining uploads for {current_user.username}: {remaining_uploads}\n")

        return jsonify({
            'tier': tier.name,
            'daily_limit': tier.daily_limit,
            'uploads_used': uploads_today,
            'uploads_left': remaining_uploads,
            'reset_in_seconds': int((start_of_day_ts + 86400) - time.time())
        }), 200

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
            return jsonify({'status': 'error', 'message': 'No image provided.'}), 400

        # Check if the user exists
        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            logger.error(f"User {user.username} not found.\n")
            return jsonify({"status": "error", "message": f"User {user.username} not found."}), 404

        ext = os.path.splitext(file.filename)[1]
        logger.info(f"Recived filename: {file.filename}")
        # Save the original temporarily
        temp_filename  = secure_filename(f"{uuid.uuid4().hex}{ext}")
        temp_path = os.path.join(tempfile.gettempdir(), temp_filename)
        file.save(temp_path)
        # Downscale and save final image
        processed_path = preprocess_image(temp_path)
        # Final filename
        final_filename = secure_filename(f"{uuid.uuid4().hex}{ext}")
        final_filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
        # Move temp to final location
        os.rename(processed_path, final_filepath)
        logger.info(f"Saved processed image to: {final_filepath}\n")

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
            post_url="-",
            tags=content, 
            tags_vector=embedding,
            swatch_vector=swatch_vector,
            timestamp=int(time.time()),
            user_id=user.id,
        )
        session.add(entry)
        session.commit()

        return jsonify({'status': 'success', 'message': 'Uploaded and processed successfully'})
    
    except Exception as e:
        logger.error("ERROR:", str(e))
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
            return jsonify({'status': 'error', 'message': 'No image URL provided.'}), 400

        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            return jsonify({"status": "error", "message": "User not found."}), 404

        logger.info(f"Downloading image from: {image_url[:25]}")
        response = requests.get(image_url, stream=True)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch image from URL: {image_url}")

        ext = os.path.splitext(image_url)[1]
        if ext.lower() not in [".png", ".jpg", ".jpeg", ".webp"]:
            ext = ".jpg"

        temp_filename = secure_filename(f"{uuid.uuid4().hex}{ext}")
        temp_path = os.path.join(tempfile.gettempdir(), temp_filename)

        with open(temp_path, "wb") as out_file:
            out_file.write(response.content)

        processed_path = preprocess_image(temp_path)
        final_filename = secure_filename(f"{uuid.uuid4().hex}{ext}")
        final_filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
        os.rename(processed_path, final_filepath)

        IMAGE_BASE64 = [base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")]

        content = call_llm_api(
            sysprompt = IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64_list = IMAGE_BASE64
        )
        embedding = call_vec_api(content)
        swatch_vector = extract_distinct_colors(final_filepath)

        entry = DataEntry(
            file_path=final_filepath, 
            post_url=post_url,
            tags=content, 
            tags_vector=embedding,
            swatch_vector=swatch_vector,
            timestamp=int(time.time()),
            user_id=user.id,
        )
        session.add(entry)
        session.commit()

        return jsonify({'status': 'success', 'message': 'Image from URL processed successfully'})
    
    except Exception as e:
        logger.error("ERROR:", str(e))
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/upload/text', methods=['POST'])
@limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_text(current_user):
    logger.info("\nReceived request to upload text\n")

    try:
        text = request.form['text']

        # Check if the user exists
        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            logger.error(f"User {user.username} not found.\n")
            return jsonify({"status": "error", "message": f"User {user.username} not found."}), 404
        logger.info(f"Received from {user.username} a text: {text}\n")

        # Parse URL or text
        parse_type, content = parse_url_or_text(text)
        if parse_type == "text":
            selected_text = content
            
            # Final filename and move
            final_filename = secure_filename(f"{uuid.uuid4().hex}.txt")
            final_filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
            with open(final_filepath, "w") as f:
                f.write(selected_text)
            logger.info(f"Saved text to: {final_filepath}\n")

            # Create embedding
            embedding = call_vec_api(selected_text)

            # Save to database
            session = Session()
            entry = DataEntry(
                file_path=final_filepath, 
                post_url="-",
                tags=selected_text, 
                tags_vector=embedding,
                swatch_vector=None,  # No color swatch for text
                timestamp=int(time.time()),
                user_id=user.id,
            )
            session.add(entry)
            session.commit()

            return jsonify({'status': 'success', 'message': 'Text processed successfully'})
        elif parse_type == "url":
            url = content
            logger.info(f"Received URL: {url}\n")
            
            # Take screenshot
            ext = ".png"
            temp_filename = secure_filename(f"{uuid.uuid4().hex}{ext}")
            temp_path = os.path.join(tempfile.gettempdir(), temp_filename)

            logger.info(f"Taking screenshot of {url}...")
            screenshot_url(url, path=temp_path)

            # Downscale and save final image
            processed_path = preprocess_image(temp_path)

            # Final filename and move
            final_filename = secure_filename(f"{uuid.uuid4().hex}{ext}")
            final_filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
            os.rename(processed_path, final_filepath)

            logger.info(f"Saved processed image to: {final_filepath}\n")

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
                post_url=url,
                tags=content, 
                tags_vector=embedding,
                swatch_vector=swatch_vector,
                timestamp=int(time.time()),
                user_id=user.id,
            )
            session.add(entry)
            session.commit()

            return jsonify({'status': 'success', 'message': 'URL processed successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Invalid input provided.'}), 400
    
    except Exception as e:
        logger.error("ERROR:", str(e))
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/upload/pdf', methods=['POST'])
@limiter.limit("1 per second")
@token_required
@save_limit_required
def upload_pdf(current_user):
    file = request.files.get("pdf")
    if not file:
        return jsonify({"status": "error", "message": "No PDF uploaded"}), 400

    timestamped_filename = f"{file.filename}_{int(time.time())}.pdf"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], timestamped_filename)
    file.save(save_path)

    try:
        image_b64_list = generate_img_b64_list(save_path)
        if not image_b64_list:
            return jsonify({"status": "error", "message": "No pages found in PDF"}), 400

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
            post_url="-",
            tags=content,
            tags_vector=embedding,
            swatch_vector=None,
            timestamp=int(time.time()),
            user_id=current_user.id,
        )
        session.add(entry)
        session.commit()

        return jsonify({"status": "success", "message": "PDF uploaded and processed"})

    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/delete/file', methods=['POST'])
@limiter.limit("1 per second")
@token_required
def delete_file(current_user):
    try:
        logger.info("\nReceived request to delete file\n")

        file_name = request.form['file_name']
        if not file_name:
            return jsonify({'status': 'error', 'message': 'No file_name provided.'}), 400
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
        logger.info(f"Received file_path: {file_path}\n")

        # Check if the user exists
        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            logger.error(f"User {user.username} not found.\n")
            return jsonify({"status": "error", "message": f"User {user.username} not found."}), 404
        
        # Find entry with this file path and user ID
        entry = session.query(DataEntry).filter_by(file_path=file_path, user_id=user.id).first()
        if not entry:
            logger.warning(f"No entry found for file_path: {file_path}")
            return jsonify({"status": "error", "message": "No matching file entry found."}), 404

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

        return jsonify({'status': 'success', 'message': 'Deleted file successfully'})
    
    except Exception as e:
        logger.error("ERROR:", str(e))
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_file/<filename>')
@limiter.limit("5 per second;30 per minute")
@token_required
def get_file(current_user, filename):
    logger.info(f"Received request to get file: {filename}\n")
    
    # Check if the user exists
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        logger.error(f"User {user.username} not found.\n")
        return jsonify({"status": "error", "message": f"User {user.username} not found."}), 404

    # Sanitize inputs
    filename = secure_filename(filename)

    # Confirm the image exists in that user's folder
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    logger.info(f"file_path: {file_path}\n")
    if not os.path.exists(file_path):
        abort(404)

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/query', methods=['POST'])
@limiter.limit("5 per second")
@token_required
def query(current_user):
    logger.info(f"\nReceived request to query image from user of id: {current_user.id}\n")

    data = request.json
    logger.info(f"data: {data}\n")

    query_text = data.get("searchText", "").strip()
    if not query_text:
        return jsonify({"error": "searchText required"}), 400
    
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        return jsonify({"error": "Invalid user"}), 404

    userid = user.id
    logger.info(f"Querying for userid: {userid}")
    
    # Extract color
    color_code = extract_color_code(query_text)

    # Extract time and convert to timestamp
    start = time.perf_counter()
    timestamp = parse_time_input(query_text)
    unix_time = int(timestamp.timestamp()) if timestamp else None
    logger.info(f"unix_time took {time.perf_counter() - start:.2f}s")

    # Extract content after removing time & color
    cleaned_query = clean_text_of_color_and_time(query_text)
    query_vector = call_vec_api(cleaned_query) if cleaned_query else None

    # Build SELECT fields
    select_fields = ["file_path", "post_url", "tags", "timestamp"]
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
        LIMIT 10
    """

    # Build SQL
    sql = text(final_sql)
    result = session.execute(sql).fetchall()
    logger.info(f"len result: {len(result)}\n")

    return jsonify({
        "results": [
            {
                "file_name": f"{os.path.basename(r[0])}",
                "post_url": r[1],
                "tags_text": r[2],
                "timestamp_str": int(r[3]),
            }
            for r in result
        ]
    })

@app.route('/api/check', methods=['POST'])
@limiter.limit("1 per second")
@token_required
def check(current_user):
    logger.info(f"\nChecking for: {current_user.id}\n")

    data = request.json
    logger.info(f"data: {data}\n")

    query_text = data.get("searchText", "").strip()
    if not query_text:
        return jsonify({"error": "searchText required"}), 400
    
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        return jsonify({"error": "Invalid user"}), 404
    
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
# endregion
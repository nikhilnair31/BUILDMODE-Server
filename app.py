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
from functools import wraps
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, create_engine
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from playwright.sync_api import sync_playwright
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from image import (
    extract_distinct_colors
)
from browser import (
    screenshot_url
)
from pre_process import (
    preprocess_image
)
from parser import (
    parse_time_input,
    extract_color_code,
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
    User
)
from flask import (
    Flask, 
    request, 
    jsonify,
    abort,
    send_from_directory
)

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

# Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

def get_ip():
    # logger.info(f"request.headers: {dict(request.headers)}\n")
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    ip = forwarded_for.split(',')[0] if forwarded_for else request.headers.get('X-Real-IP', request.remote_addr)
    logger.info(f"Detected IP: {ip}")
    return ip

def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
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

@app.before_request
def restrict_headers():
    user_agent = request.headers.get("User-Agent", "")
    api_key = request.headers.get("X-App-Key", None)
    # logger.info(f"User-Agent: {user_agent}, API key: {api_key}")

    # Allow during development
    if "python" in user_agent.lower() or "postman" in user_agent.lower():
        return

    # Require custom header (future Android use)
    if not api_key or api_key != APP_SECRET_KEY:
        print(f"Rejected request with UA: {user_agent}, API key: {api_key}")
        abort(403, description="Forbidden: Invalid or missing headers.")

@app.route('/hello', methods=['GET'])
@limiter.limit("1 per second")
def hello():
    log_text = f"Received hello request from {get_ip()}\n"
    logger.info(log_text)
    return jsonify({"message": log_text})

@app.route('/refresh_token', methods=['POST'])
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

@app.route('/register', methods=['POST'])
@limiter.limit("1 per second")
def register():
    data = request.get_json()
    
    session = Session()
    if session.query(User).filter_by(username=data['username']).first():
        logger.error(f"User {data['username']} already exists.\n")
        return jsonify({'message': 'Username already exists'}), 400

    new_user = User(
        username=data['username'],
        created_at=int(time.time()),
        updated_at=int(time.time())
    )
    new_user.set_password(data['password'])

    session.add(new_user)
    session.commit()

    return jsonify({"status": "success", "message": "User registered successfully."}), 200

@app.route('/login', methods=['POST'])
@limiter.limit("1 per second")
def login():
    data = request.get_json()

    session = Session()
    user = session.query(User).filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        logger.error(f"Invalid credentials for user {data['username']}.\n")
        return jsonify({'message': 'Invalid credentials'}), 401

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
    
    return jsonify(
        {
            'access_token': access_token, 
            'refresh_token': refresh_token
        }
    ), 200

@app.route('/update-username', methods=['POST'])
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

@app.route('/upload/image', methods=['POST'])
@limiter.limit("1 per second")
@token_required
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
        IMAGE_BASE64 = base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")

        # Send to OpenAI for processing
        content = call_llm_api(
            sysprompt = IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64 = IMAGE_BASE64
        )

        # Create embedding
        embedding = call_vec_api(content)

        # Extract distinct colors
        swatch_vector = extract_distinct_colors(final_filepath)

        # Save to database
        session = Session()
        entry = DataEntry(
            imagepath=final_filepath, 
            posturl="-",
            response=content, 
            embedding=embedding,
            swatch_vector=swatch_vector,
            timestamp=int(time.time()),
            userid=user.id,
        )
        session.add(entry)
        session.commit()

        return jsonify({'status': 'success', 'message': 'Uploaded and processed successfully'})
    
    except Exception as e:
        logger.error("ERROR:", str(e))
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/upload/url', methods=['POST'])
@limiter.limit("1 per second")
@token_required
def upload_url(current_user):
    logger.info("\nReceived request to upload url\n")

    try:
        url = request.form['url']

        # Check if the user exists
        session = Session()
        user = session.query(User).get(current_user.id)
        if not user:
            logger.error(f"User {user.username} not found.\n")
            return jsonify({"status": "error", "message": f"User {user.username} not found."}), 404
        logger.info(f"Received from {user.username} a url: {url}\n")
        
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
        IMAGE_BASE64 = base64.b64encode(open(final_filepath, "rb").read()).decode("utf-8")

        # Send to OpenAI for processing
        content = call_llm_api(
            sysprompt = IMAGE_PREPROCESS_SYSTEM_PROMPT,
            image_b64 = IMAGE_BASE64
        )

        # Create embedding
        embedding = call_vec_api(content)

        # Extract distinct colors
        swatch_vector = extract_distinct_colors(final_filepath)

        # Save to database
        session = Session()
        entry = DataEntry(
            imagepath=final_filepath, 
            posturl=url,
            response=content, 
            embedding=embedding,
            swatch_vector=swatch_vector,
            timestamp=int(time.time()),
            userid=user.id,
        )
        session.add(entry)
        session.commit()

        return jsonify({'status': 'success', 'message': 'Got and processed successfully'})
    
    except Exception as e:
        logger.error("ERROR:", str(e))
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_image/<filename>')
@limiter.limit("5 per second;30 per minute")
@token_required
def get_image(current_user, filename):
    logger.info(f"Received request to get image: {filename}\n")
    
    # Check if the user exists
    session = Session()
    user = session.query(User).get(current_user.id)
    if not user:
        logger.error(f"User {user.username} not found.\n")
        return jsonify({"status": "error", "message": f"User {user.username} not found."}), 404

    # Sanitize inputs
    filename = secure_filename(filename)

    # Confirm the image exists in that user's folder
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(image_path):
        abort(404)

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/query', methods=['POST'])
@limiter.limit("1 per second")
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
    timestamp = parse_time_input(query_text)
    unix_time = int(timestamp.timestamp()) if timestamp else None

    # Extract content after removing time & color
    cleaned_query = clean_text_of_color_and_time(query_text)
    query_vector = call_vec_api(cleaned_query) if cleaned_query else None

    # Build SELECT fields
    select_fields = ["imagepath", "posturl", "response", "timestamp"]
    where_clauses = [f"userid = '{userid}'"]
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
        select_fields.append(f"embedding <=> '{query_vector}' AS semantic_distance")
        order_by_clauses.append("semantic_distance ASC")

    # Time filter
    if unix_time:
        logger.info(f"Detected time filter (<= {unix_time})")
        where_clauses.append(f"timestamp <= {unix_time}")

    # Build SQL
    sql = text(f"""
        SELECT {', '.join(select_fields)}
        FROM data
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {', '.join(order_by_clauses) if order_by_clauses else 'timestamp DESC'}
        LIMIT 10
    """)
    result = session.execute(sql).fetchall()
    logger.info(f"result: {result[:1]}\n")

    return jsonify({
        "results": [
            {
                "image_presigned_url": f"get_image/{os.path.basename(r[0])}",
                "post_url": r[1],
                "image_text": r[2],
                "timestamp_str": int(r[3]),
            }
            for r in result
        ]
    })
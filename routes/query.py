import os
import time
import logging
import traceback
from sqlalchemy import text
from routes import query_bp
from functools import lru_cache
from flask import request, jsonify
from core.utils.config import Config
from core.database.database import get_db_session
from core.database.models import User, DataEntry
from core.utils.logs import error_response
from core.utils.cache import query_cache, get_cache_key, clear_user_cache
from core.content.parser import parse_time_input, extract_color_code, clean_text_of_color_and_time, rgb_to_vec
from core.ai.ai import call_vec_api
from core.utils.decoraters import token_required

logger = logging.getLogger(__name__)

@lru_cache(maxsize=512)
def cached_call_vec_api(text_input):
    """Cached version of call_vec_api."""
    return call_vec_api(text_input)

@query_bp.route('/get_similar/<filename>')
# @limiter.limit("5 per second;30 per minute")
@token_required
def get_similar(current_user, filename):
    session = get_db_session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)

        # filename is already secure_filename'd by the caller for path safety
        # We need the full path to match the DataEntry file_path
        file_path_for_query = os.path.join(Config.UPLOAD_DIR, filename) # Assuming Config is imported if needed

        entry = session.query(DataEntry).filter_by(file_path=file_path_for_query, user_id=user.id).first()
        if not entry:
            e = f"No entry found for file_path: {file_path_for_query}"
            logger.error(e)
            return error_response(e, 404)
        
        user_id = user.id
        query_vec = entry.tags_vector.tolist()

        final_sql = f"""
            SELECT file_path, thumbnail_path, post_url, tags_vector <=> '{query_vec}' AS similarity
            FROM data
            WHERE user_id = {user_id} AND file_path != '{entry.file_path}'
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
                    "thumbnail_name": os.path.basename(r[1]) if r[1] else None,
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

@query_bp.route('/query', methods=['POST'])
# @limiter.limit("5 per second")
@token_required
def query(current_user):
    logger.info(f"\nReceived request to query from user of id: {current_user.id}\n")
    data = request.json
    query_text = data.get("searchText", "").strip()
    if not query_text:
        e = "searchText required"
        logger.error(e)
        return error_response(e, 400)
    
    cache_key = get_cache_key(current_user.id, query_text)
    if cache_key in query_cache:
        logger.info("Serving /api/query from cache.")
        return jsonify(query_cache[cache_key])
    
    session = get_db_session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)

    userid = user.id
    logger.info(f"Querying for userid: {userid}")
    
    color_code = extract_color_code(query_text)
    start_time_parse = time.perf_counter()
    user_tz = user.timezone if user and user.timezone else 'UTC'
    timestamp = parse_time_input(query_text, user_tz)
    unix_time = int(timestamp.timestamp()) if timestamp else None
    logger.info(f"Time parsing took {(time.perf_counter() - start_time_parse) * 1000:.2f}ms")

    cleaned_query = clean_text_of_color_and_time(query_text)
    query_vector = cached_call_vec_api(cleaned_query) if cleaned_query else None

    select_fields = ["file_path", "thumbnail_path", "post_url"]
    where_clauses = [f"user_id = '{userid}'"]
    order_by_clauses = []

    if color_code:
        logger.info("Detected color input")
        swatch_vector = color_code if isinstance(color_code, str) and color_code.startswith("#") else rgb_to_vec(color_code)
        select_fields.append(f"swatch_vector <-> '{swatch_vector}' AS color_distance")
        order_by_clauses.append("color_distance ASC")

    if query_vector:
        logger.info("Detected content input")
        select_fields.append(f"tags_vector <=> '{query_vector}' AS semantic_distance")
        order_by_clauses.append("semantic_distance ASC")

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
    sql = text(final_sql)
    result = session.execute(sql).fetchall()
    logger.info(f"len result: {len(result)}\n")

    result_json = {
        "results": [
            {
                "file_name": os.path.basename(r[0]),
                "thumbnail_name": os.path.basename(r[1]) if r[1] else None,
                "post_url": r[2]
            }
            for r in result
        ]
    }

    query_cache[cache_key] = result_json
    return jsonify(result_json)

@query_bp.route('/check', methods=['POST'])
# @limiter.limit("1 per second")
@token_required
def check(current_user):
    logger.info(f"\nChecking for: {current_user.id}\n")
    data = request.json
    query_text = data.get("searchText", "").strip()
    if not query_text:
        e = "searchText required"
        logger.error(e)
        return error_response(e, 400)
    
    session = get_db_session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)
    
    color_code = extract_color_code(query_text)
    timestamp = parse_time_input(query_text)
    unix_time = int(timestamp.timestamp()) if timestamp else None

    cleaned_query = clean_text_of_color_and_time(query_text)
    query_vector = cached_call_vec_api(cleaned_query) if cleaned_query else None

    select_fields = ["file_path", "post_url", "tags", "timestamp"]
    where_clauses = [f"user_id = '{user.id}'"]
    order_by_clauses = []

    if color_code:
        logger.info("Detected color input")
        swatch_vector = color_code if isinstance(color_code, str) and color_code.startswith("#") else rgb_to_vec(color_code)
        select_fields.append(f"swatch_vector <-> '{swatch_vector}' AS color_distance")
        order_by_clauses.append("color_distance ASC")

    if query_vector:
        logger.info("Detected content input")
        select_fields.append(f"tags_vector <=> '{query_vector}' AS semantic_distance")
        order_by_clauses.append("semantic_distance ASC")

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

    sql = text(final_sql)
    result = session.execute(sql).fetchall()
    logger.info(f"result: {result[:1]}\n")

    useful_content = len(result) > 0
    return jsonify({
        "results": {
            "useful": useful_content,
            "query": query_text,
        }
    }), 200
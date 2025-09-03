# query.py

import os
import time
import logging
import traceback
from sqlalchemy import bindparam, text
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

# ---------------------------------- CACHING ------------------------------------

@lru_cache(maxsize=512)
def cached_call_vec_api(text_input):
    """Cached version of call_vec_api."""
    return call_vec_api(query_text=text_input, task_type = "RETRIEVAL_QUERY")

# ---------------------------------- SIMILARITY ------------------------------------

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
            SELECT file_path, thumbnail_path, tags_vector <=> '{query_vec}' AS similarity
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
                    "thumbnail_name": os.path.basename(r[1]) if r[1] else None
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

# ---------------------------------- QUERYING ------------------------------------

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
    logger.info(f"Querying for userid: {userid} - query_text: {query_text}")
    
    # ---------------- New ----------------

    vec_query = cached_call_vec_api(query_text)

    sql = text("""
        WITH bounds AS (
            SELECT 
                MIN(timestamp) AS min_ts,
                MAX(timestamp) AS max_ts
            FROM data
            WHERE user_id = :userid
        ),
        scored AS (
            SELECT 
                file_path,
                thumbnail_path,
                tags,
                ts_rank(to_tsvector('english', tags), plainto_tsquery('english', :fts_query)) AS text_rank,
                tags_vector <=> (:vec_query)::vector AS distance,
                GREATEST(
                    word_similarity(lower(tags), lower(:trgm_query)),
                    similarity(lower(tags), lower(:trgm_query))
                ) AS trgm_sim,
                (timestamp - bounds.min_ts)::float / NULLIF(bounds.max_ts - bounds.min_ts, 0) AS recency
            FROM data, bounds
            WHERE user_id = :userid
        )
        
        SELECT
            *,
            (0.43 * text_rank) 
            + (0.43 * (1 - distance)) 
            + (0.10 * trgm_sim) 
            + (0.04 * recency) AS hybrid_score
        FROM scored
        WHERE
            text_rank > 0.05
            and DISTANCE < 1
            AND trgm_sim > 0.01
        ORDER BY distance ASC
    """)
    params = {
        "userid": userid,
        "fts_query": query_text,
        "trgm_query": query_text,
        "vec_query": vec_query
    }

    result = session.execute(sql, params).fetchmany(100)
    logger.info(f"len result: {len(result)}\n")
    logger.info(f"result\n")
    for i, row in enumerate(result):
        logger.info(f"{i}\n{row}\n{"-"*60}")

    result_json = {
        "results": [
            {
                "file_name": os.path.basename(r[0]),
                "thumbnail_name": os.path.basename(r[1]) if r[1] else None,
                "tags": r[2]
            }
            for r in result
        ]
    }

    query_cache[cache_key] = result_json
    return jsonify(result_json)

# ---------------------------------- QUERYING ------------------------------------

@query_bp.route('/check/text', methods=['POST'])
# @limiter.limit("5 per second")
@token_required
def check_text(current_user):
    logger.info(f"\nReceived request to check using text from user of id: {current_user.id}\n")
    
    data = request.json
    check_text = data.get("searchText", "").strip()
    if not check_text:
        e = "searchText required"
        logger.error(e)
        return error_response(e, 400)
    
    cache_key = get_cache_key(current_user.id, check_text)
    if cache_key in query_cache:
        logger.info("Serving /api/check/text from cache.")
        return jsonify(query_cache[cache_key])
    
    session = get_db_session()
    user = session.query(User).get(current_user.id)
    if not user:
        e = f"User ID {current_user.id} not found"
        logger.error(e)
        return error_response(e, 404)

    userid = user.id
    logger.info(f"Checking for userid: {userid}")
    
    
    # ---------------- New ----------------

    vec_query = cached_call_vec_api(check_text)
    sql = text("""
        WITH bounds AS (
            SELECT 
                MIN(timestamp) AS min_ts,
                MAX(timestamp) AS max_ts
            FROM data
            WHERE user_id = :userid
        ),
        scored AS (
            SELECT 
                file_path,
                thumbnail_path,
                tags,
                ts_rank(to_tsvector('english', tags), plainto_tsquery('english', :fts_query)) AS text_rank,
                tags_vector <=> (:vec_query)::vector AS distance,
                GREATEST(
                    word_similarity(lower(tags), lower(:trgm_query)),
                    similarity(lower(tags), lower(:trgm_query))
                ) AS trgm_sim,
                (timestamp - bounds.min_ts)::float / NULLIF(bounds.max_ts - bounds.min_ts, 0) AS recency
            FROM data, bounds
            WHERE user_id = :userid
        )
        
        SELECT
            *,
            (0.43 * text_rank) 
            + (0.43 * (1 - distance)) 
            + (0.10 * trgm_sim) 
            + (0.04 * recency) AS hybrid_score
        FROM scored
        WHERE
            text_rank > 0.05
            and DISTANCE < 1
            AND trgm_sim > 0.01
        ORDER BY distance ASC
    """)
    params = {
        "userid": userid,
        "fts_query": check_text,
        "trgm_query": check_text,
        "vec_query": vec_query
    }

    result = session.execute(sql, params).fetchall()
    logger.info(f"len result: {len(result)}\n")

    result_json = {
        "results": [
            {
                "file_name": os.path.basename(r[0]),
                "thumbnail_name": os.path.basename(r[1]) if r[1] else None
            }
            for r in result
        ]
    }

    query_cache[cache_key] = result_json
    return jsonify(result_json)

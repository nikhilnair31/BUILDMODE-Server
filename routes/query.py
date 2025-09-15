# query.py

import os, logging, traceback
from time import perf_counter
from sqlalchemy import text
from core.content.parser import extract_color_filter
from routes import query_bp
from functools import lru_cache
from flask import request, jsonify
from core.utils.config import Config
from core.database.database import get_db_session
from core.database.models import User, DataEntry
from core.ai.ai import call_vec_api
from core.utils.logs import error_response
from core.utils.timing import timed_route
from core.utils.decoraters import token_required
from core.utils.cache import query_cache, get_cache_key
from core.content.parser import extract_time_filter, sanitize_tsquery

logger = logging.getLogger(__name__)

# ---------------------------------- CACHING ------------------------------------

@lru_cache(maxsize=512)
@timed_route("cached_call_vec_api")
def cached_call_vec_api(text_input):
    """Cached version of call_vec_api."""
    return call_vec_api(query_text=text_input, task_type = "RETRIEVAL_QUERY")

# ---------------------------------- SIMILARITY ------------------------------------

@query_bp.route('/get_similar/<filename>')
# @limiter.limit("5 per second;30 per minute")
@timed_route("get_similar")
@token_required
def get_similar_to_file(current_user, filename):
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

@query_bp.route('/get_similar_to_content', methods=['POST'])
# @limiter.limit("5 per second;30 per minute")
@timed_route("get_similar_to_content")
@token_required
def get_similar_to_content(current_user):
    logger.info(f"Get similar to content for user: {current_user.id}")

    session = get_db_session()
    try:
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        data = request.json
        image_b64 = data.get("image_b64")
        if not image_b64:
            logger.error("No image_b64 provided.")
            return error_response("No image_b64 provided.", 400)

        extracted_content_text = call_llm_api(image_b64=image_b64)
        if not extracted_content_text:
            logger.error("Failed to extract content from image.")
            return error_response("Failed to extract content from image for similarity search.", 500)
            
        query_vec = call_vec_api(query_text=extracted_content_text, task_type="RETRIEVAL_QUERY")
        if not query_vec:
            logger.error("Failed to generate vector from image content.")
            return error_response("Failed to generate vector for similarity search from image.", 500)

        sql = text("""
            WITH
            -- Vector leg
            vec_leg AS (
                SELECT d.id
                FROM data d
                WHERE 
                    d.user_id = :userid
                    AND :vec_query IS NOT NULL
                    AND (d.tags_vector <=> (:vec_query)::vector) <= 1
            ),
            candidates AS (
                SELECT id FROM vec_leg
            ),
            scored AS (
                SELECT 
                    d.id,
                    d.file_path,
                    d.thumbnail_path,
                    d.tags,
                    d.timestamp,
                    TO_TIMESTAMP(d.timestamp) AS converted_date,
                    CASE 
                        WHEN :vec_query IS NOT NULL 
                        THEN d.tags_vector <=> (:vec_query)::vector 
                        ELSE 1
                    END AS distance,
                    (d.timestamp - b.min_ts)::float / NULLIF(b.max_ts - b.min_ts, 0) AS recency
                FROM candidates d
                WHERE tags IS NOT NULL
            )
            SELECT
                id,
                file_path,
                thumbnail_path,
                tags,
                timestamp,
                converted_date,
                distance,
                recency,
                (0.95 * (1 - LEAST(distance, 1)))
                + (0.005 * recency) AS hybrid_score
            FROM scored
            ORDER BY hybrid_score DESC
            LIMIT 1000
        """)
        params = {
            "user_id": user.id,
            "query_vec": query_vec,
        }

        results = session.execute(sql, params).fetchmany(1000)
        logger.info(f"Found {len(results)} similar entries")

        return jsonify({
            "results": [
                {
                    "file_id": r[0],
                    "file_name": os.path.basename(r[1]),
                    "thumbnail_name": os.path.basename(r[2]) if r[2] else None,
                    "tags": r[3]
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
@timed_route("query")
@token_required
def query(current_user):
    logger.info(f"Received request to query from user of id: {current_user.id}")
    
    try:
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
        
        query_wo_time_text, time_filter = extract_time_filter(query_text)
        logger.info(f"query_wo_time_text: {query_wo_time_text} - time_filter: {time_filter}")
        
        query_wo_col_text, color_lab = extract_color_filter(query_wo_time_text)
        has_color = color_lab is not None
        logger.info(f"query_wo_col_text: {query_wo_col_text} - color_lab: {color_lab} - has_color: {has_color}")

        struc_query_text = sanitize_tsquery(query_wo_col_text) if query_wo_col_text else ""
        logger.info(f"struc_query_text: {struc_query_text}")

        vec_query = cached_call_vec_api(query_wo_col_text) if query_wo_col_text else None

        sql = text("""
            WITH bounds AS (
                SELECT 
                    MIN(timestamp) AS min_ts,
                    MAX(timestamp) AS max_ts
                FROM data
                WHERE user_id = :userid
            ),
            -- FTS leg
            fts_leg AS (
                SELECT d.id
                FROM data d
                WHERE 
                    d.user_id = :userid
                    AND (:start_ts IS NULL OR d.timestamp >= :start_ts)
                    AND (:end_ts   IS NULL OR d.timestamp <= :end_ts)
                    AND :fts_query <> ''
                    AND ts_rank(to_tsvector('english', d.tags), to_tsquery('english', :fts_query)) >= 0.05
            ),
            -- Vector leg
            vec_leg AS (
                SELECT d.id
                FROM data d
                WHERE 
                    d.user_id = :userid
                    AND (:start_ts IS NULL OR d.timestamp >= :start_ts)
                    AND (:end_ts   IS NULL OR d.timestamp <= :end_ts)
                    AND :vec_query IS NOT NULL
                    AND (d.tags_vector <=> (:vec_query)::vector) <= 1
            ),
            -- Trigram leg
            trgm_leg AS (
                SELECT d.id
                FROM data d
                WHERE 
                    d.user_id = :userid
                    AND (:start_ts IS NULL OR d.timestamp >= :start_ts)
                    AND (:end_ts   IS NULL OR d.timestamp <= :end_ts)
                    AND :trgm_query <> ''
                    AND GREATEST(
                            word_similarity(lower(d.tags), lower(:trgm_query)),
                            similarity(lower(d.tags),      lower(:trgm_query))
                        ) >= 0.01
            ),
            time_leg AS (
                SELECT d.id
                FROM data d
                WHERE d.user_id = :userid
                AND (:start_ts IS NULL OR d.timestamp >= :start_ts)
                AND (:end_ts   IS NULL OR d.timestamp <= :end_ts)
            ),
            color_leg AS (
                SELECT 
                    dc.data_id AS id,
                    MIN(dc.color_vector <-> (:color_lab)::vector) AS dist
                FROM data_color dc
                WHERE 
                    :has_color = TRUE
                    AND dc.color_vector IS NOT NULL
                GROUP BY dc.data_id
            ),
            candidates AS (
                SELECT id FROM fts_leg
                UNION
                SELECT id FROM vec_leg
                UNION
                SELECT id FROM trgm_leg
                UNION
                SELECT id FROM color_leg
                UNION
                SELECT id FROM time_leg
            ),
            scored AS (
                SELECT 
                    d.id,
                    d.file_path,
                    d.thumbnail_path,
                    d.tags,
                    d.timestamp,
                    TO_TIMESTAMP(d.timestamp) AS converted_date,
                    CASE 
                        WHEN :fts_query <> '' 
                        THEN ts_rank(to_tsvector('english', d.tags), plainto_tsquery('english', :fts_query))
                        ELSE 0
                    END AS text_rank,
                    CASE 
                        WHEN :vec_query IS NOT NULL 
                        THEN d.tags_vector <=> (:vec_query)::vector 
                        ELSE 1
                    END AS distance,
                    CASE 
                        WHEN :trgm_query <> '' 
                        THEN GREATEST(
                            word_similarity(lower(d.tags), lower(:trgm_query)),
                            similarity(lower(d.tags),      lower(:trgm_query))
                        )
                        ELSE 0
                    END AS trgm_sim,
                    cl.dist AS color_dist,
                    (d.timestamp - b.min_ts)::float / NULLIF(b.max_ts - b.min_ts, 0) AS recency
                FROM data d
                JOIN candidates c ON c.id = d.id
                CROSS JOIN bounds b
                LEFT JOIN color_leg cl ON cl.id = d.id
                WHERE tags IS NOT NULL
            )
            SELECT
                id,
                file_path,
                thumbnail_path,
                tags,
                timestamp,
                
                converted_date,
                text_rank,
                distance,
                trgm_sim,
                color_dist,
                recency,
                (0.35 * text_rank)
                + (0.40 * (1 - LEAST(distance, 1)))
                + (0.15 * trgm_sim)
                + (0.005 * recency)
                + (0.10 * (CASE WHEN :has_color = TRUE THEN 1 - LEAST(color_dist/100.0,1) ELSE 0 END)) AS hybrid_score
            FROM scored
            ORDER BY hybrid_score DESC
            LIMIT 1000
        """)
        params = {
            "userid": userid,
            "fts_query": struc_query_text,
            "trgm_query": query_wo_col_text,
            "vec_query": vec_query,
            "start_ts": time_filter[0] if time_filter else None,
            "end_ts": time_filter[1] if time_filter else None,
            "has_color": has_color,
            "color_lab": color_lab if color_lab else [0,0,0],
        }

        result = session.execute(sql, params).fetchmany(1000)
        logger.info(f"len result: {len(result)}")
        # logger.info(f"result")
        for i, row in enumerate(result[:25]):
            logger.info(f"{i}")
            logger.info(f"id: {row[0]} | file_path: {row[1]}")
            logger.info(f"tags: {row[3][:200]}")
            logger.info(f"converted_date: {row[5]}")
            logger.info(f"text_rank: {row[6]} | distance: {row[7]} | trgm_sim: {row[8]} | color_dist: {row[9]} | recency: {row[10]} | hybrid_score: {row[11]}")
            logger.info(f"{"-"*50}")

        result_json = {
            "results": [
                {
                    "file_id": r[0],
                    "file_name": os.path.basename(r[1]),
                    "thumbnail_name": os.path.basename(r[2]) if r[2] else None,
                    "tags": r[3]
                }
                for r in result
            ]
        }

        query_cache[cache_key] = result_json
        return jsonify(result_json)
    except Exception as e:
        e = f"Error fetching similar content: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        session.close()

# ---------------------------------- QUERYING ------------------------------------

@query_bp.route('/check/text', methods=['POST'])
# @limiter.limit("5 per second")
@timed_route("check_text")
@token_required
def check_text(current_user):
    logger.info(f"Received request to check using text from user of id: {current_user.id}")
    
    data = request.json
    check_text = data.get("searchText", "").strip()
    if not check_text:
        e = "searchText required"
        logger.error(e)
        return error_response(e, 400)
    logger.info(f"check check_text: {check_text}")
    
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

    # query_wo_time_text, time_filter = extract_time_filter(check_text)
    # logger.info(f"query_wo_time_text: {query_wo_time_text} - time_filter: {time_filter}")

    # cleaned_query_text = sanitize_tsquery(query_wo_time_text) if query_wo_time_text else ""
    # logger.info(f"cleaned_query_text: {cleaned_query_text}")

    vec_query = cached_call_vec_api(check_text) if check_text else None

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
                timestamp, 
                TO_TIMESTAMP(timestamp) AS converted_date,
                CASE 
                    WHEN :fts_query <> '' 
                    THEN ts_rank(to_tsvector('english', tags), plainto_tsquery('english', :fts_query))
                    ELSE 1
                END AS text_rank,
                CASE 
                    WHEN :vec_query IS NOT NULL 
                    THEN tags_vector <=> (:vec_query)::vector 
                    ELSE 0
                END AS distance,
                CASE 
                    WHEN :trgm_query <> '' 
                    THEN GREATEST(
                            word_similarity(lower(tags), lower(:trgm_query)),
                            similarity(lower(tags), lower(:trgm_query))
                        )
                    ELSE 1
                END AS trgm_sim,
                (timestamp - bounds.min_ts)::float / NULLIF(bounds.max_ts - bounds.min_ts, 0) AS recency
            FROM data, bounds
            WHERE
                user_id = :userid
                AND (
                    (:start_ts IS NULL OR timestamp >= :start_ts)
                    AND
                    (:end_ts   IS NULL OR timestamp <= :end_ts)
                )
        )
        
        SELECT
            *,
                (0.40 * text_rank) 
            +   (0.46 * (1 - distance)) 
            +   (0.10 * trgm_sim) 
            +   (0.04 * recency) AS hybrid_score
        FROM scored
        WHERE
            text_rank >= 0.05
            and DISTANCE <= 1
            AND trgm_sim >= 0.01
        ORDER BY distance ASC
    """)
    params = {
        "userid": userid,
        "fts_query": check_text,
        "trgm_query": check_text,
        "vec_query": vec_query,
        "start_ts": None,
        "end_ts": None
    }

    result = session.execute(sql, params).fetchmany(10)
    logger.info(f"len result: {len(result)}")

    result_json = {
        "results": [
            {
                "file_name": os.path.basename(r[0]),
                "thumbnail_name": os.path.basename(r[1]) if r[1] else None,
                "tags": r[2],
            }
            for r in result
        ]
    }

    query_cache[cache_key] = result_json
    return jsonify(result_json)

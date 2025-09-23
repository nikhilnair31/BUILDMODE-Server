# query.py

import os, logging, traceback
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
from core.utils.cache import get_cache_value, store_cache
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

# ---------------------------------- QUERYING ------------------------------------

@query_bp.route('/query', methods=['POST'])
# @limiter.limit("5 per second")
@timed_route("query")
@token_required
def query(current_user):
    logger.info(f"Received request to query from user of id: {current_user.id}")
    
    session = None

    try:
        data = request.json
        query_text = data.get("searchText", "").strip()
        if not query_text:
            e = "searchText required"
            logger.error(e)
            return error_response(e, 400)
        
        cached = get_cache_value(current_user.id, query_text)
        if cached:
            logger.info("Serving /api/query from cache.")
            return jsonify(cached)
        
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # ---------------- Query Text Processing ----------------
        query_wo_time_text, time_filter = extract_time_filter(query_text, user.timezone)
        logger.info(f"query_wo_time_text: {query_wo_time_text}")
        logger.info(f"time_filter: {time_filter}")
        query_wo_col_text, color_lab = extract_color_filter(query_wo_time_text)
        logger.info(f"query_wo_col_text: {query_wo_col_text}")
        logger.info(f"color_lab: {color_lab}")

        struc_query_text = sanitize_tsquery(query_wo_col_text) if query_wo_col_text else ""
        logger.info(f"struc_query_text: {struc_query_text}")
        vec_query = cached_call_vec_api(query_wo_col_text) if query_wo_col_text else None
        
        # Determine if each search method is active based on query input
        is_fts_active = bool(struc_query_text)
        is_vec_active = vec_query is not None and len(vec_query) > 0 # check for non-empty vec
        is_trgm_active = bool(query_wo_col_text) # Use the raw text for trigram
        is_time_active = time_filter is not None
        is_color_active = color_lab is not None

        sql = text(f"""
            WITH bounds AS (
                SELECT 
                    MIN(timestamp) AS min_ts,
                    MAX(timestamp) AS max_ts
                FROM data
                WHERE user_id = :userid
            ),
            scored_data AS (
                SELECT 
                    d.id,
                    d.file_path,
                    d.thumbnail_path,
                    d.tags,
                    d.timestamp,
                    
                    -- Always calculate these values, but their contribution to hybrid_score
                    -- will be zero if the corresponding search method is not active.
                    
                    CASE 
                        WHEN :is_fts_active
                        THEN ts_rank(to_tsvector('english', d.tags), to_tsquery('english', :fts_query))
                        ELSE 0
                    END AS text_rank,

                    CASE 
                        WHEN :is_vec_active
                        THEN d.tags_vector <=> (:vec_query)::vector 
                        ELSE 1.0 -- Max distance for non-active vector search
                    END AS distance,

                    CASE 
                        WHEN :is_trgm_active
                        THEN GREATEST(
                            word_similarity(lower(d.tags), lower(:trgm_query)),
                            similarity(lower(d.tags), lower(:trgm_query))
                        )
                        ELSE 0
                    END AS trgm_sim,
                    
                    -- Only join data_color if color search is active
                    CASE 
                        WHEN :is_color_active 
                        THEN (
                            SELECT MIN(dc.color_vector <-> (:color_lab)::vector)
                            FROM data_color dc
                            WHERE dc.data_id = d.id AND dc.color_vector IS NOT NULL
                        )
                        ELSE NULL
                    END AS color_dist,
                    
                    -- Recency only if min_ts and max_ts are valid
                    CASE
                        WHEN b.max_ts IS NOT NULL AND b.min_ts IS NOT NULL AND b.max_ts > b.min_ts
                        THEN (d.timestamp - b.min_ts)::float / (b.max_ts - b.min_ts)
                        ELSE 0
                    END AS recency_score,
                    
                    -- Combine all scores into a hybrid score
                        (0.35 * (CASE WHEN :is_fts_active THEN ts_rank(to_tsvector('english', d.tags), to_tsquery('english', :fts_query)) ELSE 0 END))
                    +   (0.40 * (CASE WHEN :is_vec_active THEN (1 - (d.tags_vector <=> (:vec_query)::vector)) ELSE 0 END))
                    +   (0.15 * (CASE WHEN :is_trgm_active THEN GREATEST(word_similarity(lower(d.tags), lower(:trgm_query)), similarity(lower(d.tags), lower(:trgm_query))) ELSE 0 END))
                    +   (0.005 * (CASE WHEN b.max_ts IS NOT NULL AND b.min_ts IS NOT NULL AND b.max_ts > b.min_ts THEN (d.timestamp - b.min_ts)::float / (b.max_ts - b.min_ts) ELSE 0 END))
                    +   (0.10 * (CASE WHEN :is_color_active THEN (1 - LEAST((
                            SELECT MIN(dc.color_vector <-> (:color_lab)::vector)
                            FROM data_color dc
                            WHERE dc.data_id = d.id AND dc.color_vector IS NOT NULL
                        )/100.0, 1)) ELSE 0 END)) 
                    AS hybrid_score
                FROM data d
                CROSS JOIN bounds b
                WHERE 
                    d.user_id = :userid
                    AND (:start_ts IS NULL OR d.timestamp >= :start_ts)
                    AND (:end_ts IS NULL OR d.timestamp <= :end_ts)
                    AND (
                        -- allow time-only queries to return rows
                        :is_time_active
                        OR :is_color_active
                        OR (
                            (:is_fts_active  AND ts_rank(to_tsvector('english', d.tags), to_tsquery('english', :fts_query)) >= 0.05)
                            OR (:is_vec_active AND (d.tags_vector <=> (:vec_query)::vector) < 1.0)
                            OR (:is_trgm_active AND GREATEST(word_similarity(lower(d.tags), lower(:trgm_query)), similarity(lower(d.tags), lower(:trgm_query))) >= 0.01)
                        )
                    )
            )
            SELECT
                id,
                file_path,
                thumbnail_path,
                tags,
                timestamp,
                hybrid_score
            FROM scored_data
            ORDER BY hybrid_score DESC
            LIMIT :result_limit
        """)
        params = {
            "userid": user.id,
            "fts_query": struc_query_text,
            "trgm_query": query_wo_col_text,
            "vec_query": vec_query,
            "start_ts": time_filter[0] if time_filter else None,
            "end_ts": time_filter[1] if time_filter else None,
            "color_lab": color_lab if color_lab else [0,0,0],
            "is_time_active": is_time_active,
            "is_fts_active": is_fts_active, # Pass activation flags to SQL
            "is_vec_active": is_vec_active,
            "is_trgm_active": is_trgm_active,
            "is_color_active": is_color_active,
            "result_limit": 100 # Apply limit directly
        }
        # logger.info(f"params: {params}")
        result = session.execute(sql, params).fetchall()

        logger.info(f"len result: {len(result)}")
        # logger.info(f"result: {result}")

        # for i, row in enumerate(result[:25]):
        #     logger.info(f"{i}")
        #     logger.info(f"id: {row[0]} | file_path: {row[1]}")
        #     logger.info(f"tags: {row[3][:200]}")
        #     logger.info(f"converted_date: {row[5]}")
        #     logger.info(f"text_rank: {row[6]} | distance: {row[7]} | trgm_sim: {row[8]} | color_dist: {row[9]} | recency: {row[10]} | hybrid_score: {row[11]}")
        #     logger.info(f"{"-"*50}")

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

        store_cache(current_user.id, query_text, result_json)
        
        return jsonify(result_json)
    except Exception as e:
        e = f"Error with query: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        if session is not None:
            session.close()

@query_bp.route('/relevant', methods=['POST'])
# @limiter.limit("5 per second")
@timed_route("relevant")
@token_required
def relevant(current_user):
    logger.info(f"Received request for relevant using text from user of id: {current_user.id}")
    
    session = None
    
    try:
        data = request.json
        relevant_text = data.get("searchText", "").strip()
        if not relevant_text:
            e = "searchText required"
            logger.error(e)
            return error_response(e, 400)
        logger.info(f"relevant_text: {relevant_text}")
        
        cached = get_cache_value(current_user.id, relevant_text)
        if cached:
            logger.info("Serving /api/query from cache.")
            return jsonify(cached)
        
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        if not user:
            e = f"User ID {current_user.id} not found"
            logger.error(e)
            return error_response(e, 404)
        
        # ---------------- Query Text Processing ----------------
        query_wo_time_text, time_filter = extract_time_filter(relevant_text, user.timezone)
        query_wo_col_text, color_lab = extract_color_filter(query_wo_time_text)
        has_color = color_lab is not None

        struc_query_text = sanitize_tsquery(query_wo_col_text) if query_wo_col_text else ""
        vec_query = cached_call_vec_api(query_wo_col_text) if query_wo_col_text else None
        
        # Determine if each search method is active based on query input
        is_fts_active = bool(struc_query_text)
        is_vec_active = vec_query is not None and len(vec_query) > 0 # check for non-empty vec
        is_trgm_active = bool(query_wo_col_text) # Use the raw text for trigram
        is_time_active = time_filter is not None
        is_color_active = has_color

        sql = text(f"""
            WITH bounds AS (
                SELECT 
                    MIN(timestamp) AS min_ts,
                    MAX(timestamp) AS max_ts
                FROM data
                WHERE user_id = :userid
            ),
            scored_data AS (
                SELECT 
                    d.id,
                    d.file_path,
                    d.thumbnail_path,
                    d.tags,
                    d.timestamp,
                    -- Always calculate these values, but their contribution to hybrid_score
                    -- will be zero if the corresponding search method is not active.
                    CASE 
                        WHEN :is_fts_active
                        THEN ts_rank(to_tsvector('english', d.tags), to_tsquery('english', :fts_query))
                        ELSE 0
                    END AS text_rank,
                    CASE 
                        WHEN :is_vec_active
                        THEN d.tags_vector <=> (:vec_query)::vector 
                        ELSE 1.0 -- Max distance for non-active vector search
                    END AS distance,
                    CASE 
                        WHEN :is_trgm_active
                        THEN GREATEST(
                            word_similarity(lower(d.tags), lower(:trgm_query)),
                            similarity(lower(d.tags), lower(:trgm_query))
                        )
                        ELSE 0
                    END AS trgm_sim,
                    -- Only join data_color if color search is active
                    CASE 
                        WHEN :is_color_active THEN (
                            SELECT MIN(dc.color_vector <-> (:color_lab)::vector)
                            FROM data_color dc
                            WHERE dc.data_id = d.id AND dc.color_vector IS NOT NULL
                        )
                        ELSE NULL
                    END AS color_dist,
                    -- Recency only if min_ts and max_ts are valid
                    CASE
                        WHEN b.max_ts IS NOT NULL AND b.min_ts IS NOT NULL AND b.max_ts > b.min_ts
                        THEN (d.timestamp - b.min_ts)::float / (b.max_ts - b.min_ts)
                        ELSE 0
                    END AS recency_score,
                    -- Combine all scores into a hybrid score
                    (0.35 * (CASE WHEN :is_fts_active THEN ts_rank(to_tsvector('english', d.tags), to_tsquery('english', :fts_query)) ELSE 0 END))
                    + (0.40 * (CASE WHEN :is_vec_active THEN (1 - (d.tags_vector <=> (:vec_query)::vector)) ELSE 0 END))
                    + (0.15 * (CASE WHEN :is_trgm_active THEN GREATEST(word_similarity(lower(d.tags), lower(:trgm_query)), similarity(lower(d.tags), lower(:trgm_query))) ELSE 0 END))
                    + (0.005 * (CASE WHEN b.max_ts IS NOT NULL AND b.min_ts IS NOT NULL AND b.max_ts > b.min_ts THEN (d.timestamp - b.min_ts)::float / (b.max_ts - b.min_ts) ELSE 0 END))
                    + (0.10 * (CASE WHEN :is_color_active THEN (1 - LEAST((
                                SELECT MIN(dc.color_vector <-> (:color_lab)::vector)
                                FROM data_color dc
                                WHERE dc.data_id = d.id AND dc.color_vector IS NOT NULL
                            )/100.0, 1)) ELSE 0 END)) AS hybrid_score
                FROM data d
                CROSS JOIN bounds b
                WHERE 
                    d.user_id = :userid
                    AND (d.tags IS NOT NULL) -- Always ensure tags exist
                    -- Apply time filter directly here
                    AND (:start_ts IS NULL OR d.timestamp >= :start_ts)
                    AND (:end_ts   IS NULL OR d.timestamp <= :end_ts)
                    -- Additionally, ensure at least one search method is "active" to prevent full table scan
                    AND (
                        (CASE WHEN :is_fts_active THEN ts_rank(to_tsvector('english', d.tags), to_tsquery('english', :fts_query)) ELSE 0 END) >= 0.05
                        OR
                        (CASE WHEN :is_vec_active THEN (d.tags_vector <=> (:vec_query)::vector) ELSE 1.0 END) <= 1.0
                        OR
                        (CASE WHEN :is_trgm_active THEN GREATEST(word_similarity(lower(d.tags), lower(:trgm_query)), similarity(lower(d.tags), lower(:trgm_query))) ELSE 0 END) >= 0.01
                        OR
                        :is_color_active IS TRUE -- if color search is active, the subquery will filter out non-matching colors
                    )
            )
            SELECT
                id,
                file_path,
                thumbnail_path,
                tags,
                timestamp,
                hybrid_score
            FROM scored_data
            ORDER BY hybrid_score DESC
            LIMIT :result_limit
        """)
        params = {
            "userid": user.id,
            "fts_query": struc_query_text,
            "trgm_query": query_wo_col_text,
            "vec_query": vec_query,
            "start_ts": time_filter[0] if time_filter else None,
            "end_ts": time_filter[1] if time_filter else None,
            "has_color": has_color, # Used in CASE statements for score contribution
            "color_lab": color_lab if color_lab else [0,0,0],
            "is_fts_active": is_fts_active, # Pass activation flags to SQL
            "is_vec_active": is_vec_active,
            "is_trgm_active": is_trgm_active,
            "is_color_active": is_color_active,
            "result_limit": 10 # Apply limit directly
        }
        result = session.execute(sql, params).fetchall()
        logger.info(f'result\n{result[:1]}')

        result_json = {
            "results": [
                {
                    "file_name": os.path.basename(r[1]),
                    "thumbnail_name": os.path.basename(r[2]) if r[2] else None,
                    "tags": r[3],
                    "hybrid_score": r[5],
                }
                for r in result
            ]
        }
        
        store_cache(current_user.id, relevant_text, result_json)

        return jsonify(result_json)
    except Exception as e:
        e = f"Error with relevant: {e}"
        logger.error(e)
        traceback.print_exc()
        return error_response(e, 500)
    finally:
        if session is not None:
            session.close()

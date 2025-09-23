# test_explain_query.py

import os
import logging
import argparse
import traceback
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from core.content.parser import extract_color_filter, extract_time_filter, sanitize_tsquery
from core.utils.config import Config
from routes.query import cached_call_vec_api

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("test_explain_query")

engine = create_engine(Config.ENGINE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

def run_explain(query_text: str):
    session = Session()
    try:
        # ---------------- Query Text Processing ----------------
        query_wo_time_text, time_filter = extract_time_filter(query_text)
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
            "userid": 1,
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
            "result_limit": 100 # Apply limit directly
        }

        # Wrap in EXPLAIN ANALYZE
        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, VERBOSE) {sql.text}"
        result = session.execute(text(explain_sql), params)
        logger.info("=== EXPLAIN ANALYZE Output ===")
        for row in result:
            print(row[0])

    except Exception as e:
        logger.error(f"Exception running EXPLAIN: {e}")
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run EXPLAIN ANALYZE on a SQL query")
    parser.add_argument("-q", "--query", type=str, required=True, help="The SQL query to analyze")
    
    args = parser.parse_args()

    run_explain(args.query)

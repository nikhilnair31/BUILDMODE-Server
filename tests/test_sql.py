from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select, text
from core.ai.ai import call_vec_api
from core.content.parser import extract_time_filter, sanitize_tsquery
from core.database.database import get_db_session

session = get_db_session()

query_text = 'today'

query_wo_time_text, time_filter = extract_time_filter(query_text)
print(f"query_wo_time_text: {query_wo_time_text} - time_filter: {time_filter}")

cleaned_query_text = sanitize_tsquery(query_wo_time_text) if query_wo_time_text else ""
print(f"cleaned_query_text: {cleaned_query_text}")

vec_query = call_vec_api(query_text=query_text, task_type = "RETRIEVAL_QUERY") if cleaned_query_text else None
print(f"vec_query: {None if vec_query is None else vec_query[:10]}")

sql = text(f"""
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
                    THEN ts_rank(to_tsvector('english', tags), to_tsquery('english', :fts_query))
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
            (0.43 * text_rank) 
            + (0.43 * (1 - distance)) 
            + (0.10 * trgm_sim) 
            + (0.04 * recency) AS hybrid_score
        FROM scored
        WHERE
            text_rank >= 0.05
            and DISTANCE <= 1
            AND trgm_sim >= 0.01
        ORDER BY distance ASC
        LIMIT 5
""")
params = {
    "userid": 1,
    "fts_query": cleaned_query_text,
    "trgm_query": cleaned_query_text,
    "vec_query": vec_query,
    "start_ts": time_filter[0] if time_filter else None,
    "end_ts": time_filter[1] if time_filter else None
}

result = session.execute(sql, params).fetchall()
for i, row in enumerate(result):
    print(f"{i}\n{row}")
    print(f"{"-"*60}")

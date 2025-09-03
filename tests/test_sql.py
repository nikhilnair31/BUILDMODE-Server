from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select, text
from core.ai.ai import call_vec_api
from core.database.database import get_db_session

session = get_db_session()

query_text = 'car'
vec_query = call_vec_api(query_text=query_text, task_type = "RETRIEVAL_QUERY")

sql = text("""
    WITH scored AS (
        SELECT 
            file_path,
            thumbnail_path,
            tags,
            ts_rank(to_tsvector('english', tags), plainto_tsquery('english', :fts_query)) AS text_rank,
            tags_vector <=> (:vec_query)::vector AS distance,
            GREATEST(
                word_similarity(lower(tags), lower(:trgm_query)),
                similarity(lower(tags), lower(:trgm_query))
            ) AS trgm_sim
        FROM data
        WHERE user_id = :userid
    )
    
    SELECT *,
        (0.45 * text_rank) + (0.45 * (1 - distance)) + (0.10 * trgm_sim) AS hybrid_score
    FROM scored
    WHERE
        text_rank > 0.05
        and DISTANCE < 1
        AND trgm_sim > 0.01
    ORDER BY distance ASC;
""")
params = {
    "userid": 1,
    "fts_query": query_text,
    "trgm_query": query_text,
    "vec_query": vec_query
}

result = session.execute(sql, params)
for i, row in enumerate(result):
    print(f"{i}\n{row}")
    print(f"{"-"*60}")

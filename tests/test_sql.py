from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select, text
from core.ai.ai import call_vec_api
from core.database.database import get_db_session

session = get_db_session()

fts_query = 'coffee'
vec_query = call_vec_api(query_text=fts_query, task_type = "RETRIEVAL_QUERY")

sql = text("""
    SELECT 
        id,
        LEFT(tags, 100) AS tags_preview,
        ts_rank(to_tsvector('english', tags), plainto_tsquery('english', :fts_query)) AS text_rank,
        tags_vector <=> (:vec_query)::vector AS distance,
        (0.7 * ts_rank(to_tsvector('english', tags), plainto_tsquery('english', :fts_query))
        - 0.3 * (1 - (tags_vector <=> (:vec_query)::vector))) AS hybrid_score
    
    FROM data
    
    WHERE 
        ts_rank(to_tsvector('english', tags), plainto_tsquery('english', :fts_query)) > 0.05
        OR tags_vector <=> (:vec_query)::vector < 0.5
    
    ORDER BY hybrid_score DESC
    LIMIT 20;
""")
params = {"fts_query": fts_query, "vec_query": vec_query}

result = session.execute(sql, params)
for row in result:
    print(row)

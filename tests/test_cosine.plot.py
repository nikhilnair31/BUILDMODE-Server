import os
import logging
import traceback
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, create_engine
import numpy as np
import matplotlib.pyplot as plt
from sklearn.preprocessing import normalize
from core.ai.ai import (
    call_vec_api
)

load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# DB connection
MIA_DB_NAME = os.getenv("MIA_DB_NAME")
MIA_DB_PASSWORD = os.getenv("MIA_DB_PASSWORD")
ENGINE_URL = f'postgresql://postgres:{MIA_DB_PASSWORD}@localhost/{MIA_DB_NAME}'
logger.info(f"Connecting to {ENGINE_URL}")

engine = create_engine(ENGINE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Sample queries and embeddings
queries = ["dark sky", "dogs", "twitter game ui"]
embeddings = [call_vec_api(q) for q in queries]
embeddings = normalize(embeddings)  # Normalize for cosine similarity

try:
    similarity_scores = []

    for idx, vec in enumerate(embeddings):
        vec_str = '[' + ','.join(map(str, vec)) + ']'
        sql = text(f"""
            SELECT (embedding <=> '{vec_str}') AS cosine_similarity
            FROM data
            ORDER BY cosine_similarity DESC
            LIMIT 100
        """)
        results = session.execute(sql).fetchall()
        scores = [r[0] for r in results]
        similarity_scores.extend(scores)
        logger.info(f"Query '{queries[idx]}' returned {len(scores)} scores.")

    # Plot histogram to file
    output_path = "similarity_distribution.png"
    plt.figure(figsize=(10, 6))
    plt.hist(similarity_scores, bins=20, range=(0, 1), edgecolor='black')
    plt.title("Cosine Similarity Distribution")
    plt.xlabel("Cosine Similarity")
    plt.ylabel("Frequency")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(output_path)
    logger.info(f"Histogram saved to {output_path}")

except Exception as e:
    logger.error(f"Database or processing error: {e}")
    logger.error(traceback.format_exc())
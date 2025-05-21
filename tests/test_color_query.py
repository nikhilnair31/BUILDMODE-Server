
import os
import logging
import random
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, create_engine
from models import (
    DataEntry,
    User
)
from image import (
    extract_distinct_colors
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIA_DB_NAME = os.getenv("MIA_DB_NAME")
MIA_DB_PASSWORD = os.getenv("MIA_DB_PASSWORD")

ENGINE_URL = f'postgresql://postgres:{MIA_DB_PASSWORD}@localhost/{MIA_DB_NAME}'
logger.info(f"Connecting to {ENGINE_URL}\n")

engine = create_engine(ENGINE_URL)
Session = sessionmaker(bind=engine)

session = Session()

userid = 1
logger.info(f"Querying for userid: {userid}")

image_folder_path = r'./uploads'
image_files = [f for f in os.listdir(image_folder_path) if f.endswith(('.png', '.jpg', '.jpeg', '.gif'))]
final_filepath = os.path.join(image_folder_path, random.choice(image_files))
logger.info(f"Image path: {final_filepath}")

swatch_vector = extract_distinct_colors(final_filepath)

sql = text(f"""
    SELECT imagepath, posturl, response, timestamp, swatch_vector <-> '{swatch_vector}' AS distance
    FROM data
    WHERE userid = '{userid}'
    ORDER BY distance ASC
    LIMIT 3
""")
result = session.execute(sql).fetchall()

logger.info("Top 3 Matches:")
for row in result:
    logger.info(f"path: {row[0]}, distance: {row[4]:.4f}")
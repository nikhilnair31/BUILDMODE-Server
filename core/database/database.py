# database.py

import logging
from sqlalchemy import event, DDL, create_engine
from sqlalchemy.orm import sessionmaker
from core.utils.config import Config
from core.database.models import Base, DataEntry

logger = logging.getLogger(__name__)

engine = None
Session = None

create_extension = DDL("CREATE EXTENSION IF NOT EXISTS vector;")
event.listen(
    Base.metadata,
    "before_create",
    create_extension.execute_if(dialect="postgresql")
)

create_extension_trgm = DDL("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
event.listen(
    Base.metadata,
    "before_create",
    create_extension_trgm.execute_if(dialect="postgresql")
)

ivfflat_index = DDL("""
CREATE INDEX IF NOT EXISTS data_tags_vector_idx
ON data
USING ivfflat (tags_vector vector_cosine_ops)
WITH (lists = 100);
""")
event.listen(
    DataEntry.__table__,
    "after_create",
    ivfflat_index.execute_if(dialect="postgresql")
)
analyze = DDL("ANALYZE data;")
event.listen(
    DataEntry.__table__,
    "after_create",
    analyze.execute_if(dialect="postgresql")
)

fts_index = DDL("""
CREATE INDEX IF NOT EXISTS data_tags_fts_idx
ON data
USING gin (to_tsvector('english', tags));
""")
event.listen(
    DataEntry.__table__,
    "after_create",
    fts_index.execute_if(dialect="postgresql")
)

trgm_index = DDL("""
CREATE INDEX IF NOT EXISTS data_tags_trgm_idx
ON data
USING gin (lower(tags) gin_trgm_ops);
""")
event.listen(
    DataEntry.__table__,
    "after_create",
    trgm_index.execute_if(dialect="postgresql")
)

def init_db():
    global engine, Session
    if engine is None:
        logger.info(f"Connecting to database at: {Config.ENGINE_URL}")
        
        engine = create_engine(Config.ENGINE_URL)
        Session = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        logger.info("Database initialized.")

def get_db_session():
    if Session is None:
        init_db()
    return Session()
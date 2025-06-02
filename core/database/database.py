# database.py

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.utils.config import Config
from core.database.models import Base # Corrected import path

logger = logging.getLogger(__name__)

engine = None
Session = None

def init_db():
    global engine, Session
    if engine is None:
        logger.info(f"Connecting to database at: {Config.ENGINE_URL}")
        
        engine = create_engine(Config.ENGINE_URL)
        Session = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        logger.info("Database initialized.")

def get_db_session():
    """Provides a new database session."""
    if Session is None:
        init_db()
    return Session()
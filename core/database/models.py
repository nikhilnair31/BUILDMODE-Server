# models.py

from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from werkzeug.security import (
    generate_password_hash, 
    check_password_hash
)
from sqlalchemy import (
    Column, 
    Integer, 
    String,
    ForeignKey,
    Enum
)

Base = declarative_base()

class ProcessingStatus(str):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class StagingEntry(Base):
    __tablename__ = 'staging'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    file_path = Column(String)
    post_url = Column(String)
    timestamp = Column(Integer)
    source_type = Column(String)
    status = Column(String, default=ProcessingStatus.PENDING, nullable=False)

class DataEntry(Base):
    __tablename__ = 'data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    file_path = Column(String)
    thumbnail_path = Column(String)
    post_url = Column(String)
    timestamp = Column(Integer)
    tags = Column(String)
    tags_vector = Column(Vector(768))
    swatch_vector = Column(Vector(30))

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    email = Column(String)
    timezone = Column(String, default='UTC')
    password_hash = Column(String)
    created_at = Column(Integer)
    updated_at = Column(Integer)
    tier_id = Column(Integer, ForeignKey('tiers.id'), default=1)

    tier = relationship("Tier")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Tier(Base):
    __tablename__ = 'tiers'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    daily_limit = Column(Integer, nullable=False, default=10)
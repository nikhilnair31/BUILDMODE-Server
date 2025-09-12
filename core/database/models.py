# models.py

from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from werkzeug.security import (
    generate_password_hash, 
    check_password_hash
)
from sqlalchemy import (
    Boolean,
    Column,
    Date, 
    Integer, 
    String,
    ForeignKey,
    Enum
)

Base = declarative_base()

# ---------------------------------- HELPERS ------------------------------------

class ProcessingStatus(str):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Tier(Base):
    __tablename__ = 'tiers'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    daily_limit = Column(Integer, nullable=False, default=10)

class Frequency(Base):
    __tablename__ = 'frequency'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

# ---------------------------------- POST DATA ------------------------------------

class StagingEntry(Base):
    __tablename__ = 'staging'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    file_path = Column(String)
    timestamp = Column(Integer)
    source_type = Column(String)
    status = Column(String, default=ProcessingStatus.PENDING, nullable=False)

class DataEntry(Base):
    __tablename__ = 'data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    file_path = Column(String)
    thumbnail_path = Column(String)
    tags = Column(String)
    tags_vector = Column(Vector(768))
    timestamp = Column(Integer)

class DataColor(Base):
    __tablename__ = 'data_color'

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_id = Column(Integer)
    color_hex = Column(String)
    color_vector = Column(Vector(3))

# ---------------------------------- TRACKING ------------------------------------

class PostInteraction(Base):
    __tablename__ = 'post_interactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    data_id = Column(Integer, ForeignKey('data.id'))
    user_query = Column(String)

class LinkInteraction(Base):
    __tablename__ = 'link_interactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    digest_url = Column(String)
    timestamp = Column(Integer)
    
class LinkEntry(Base):
    __tablename__ = 'links'

    url = Column(String, primary_key=True)
    text = Column(String)
    author = Column(String)
    publishedDate = Column(Date)
    image = Column(String)

# ---------------------------------- USERS ------------------------------------

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
    
    summary_email_enabled = Column(Boolean, default=False)
    summary_frequency_id = Column(Integer, ForeignKey('frequency.id'), default=1)
    last_summary_sent = Column(Integer, nullable=True)
    
    digest_email_enabled = Column(Boolean, default=False)
    digest_frequency_id = Column(Integer, ForeignKey('frequency.id'), default=1)
    last_digest_sent = Column(Integer, nullable=True)

    tier = relationship("Tier")
    summary_frequency = relationship("Frequency", foreign_keys=[summary_frequency_id])
    digest_frequency = relationship("Frequency", foreign_keys=[digest_frequency_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

from werkzeug.security import (
    generate_password_hash, 
    check_password_hash
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column, 
    Integer, 
    Float,
    String
)

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    created_at = Column(Integer)
    updated_at = Column(Integer)
    tier_id = Column(Integer, default=1)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class DataEntry(Base):
    __tablename__ = 'data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(String)
    post_url = Column(String)
    tags = Column(String)
    tags_vector = Column(Vector(768))
    swatch_vector = Column(Vector(30))
    timestamp = Column(Integer)
    user_id = Column(Integer)
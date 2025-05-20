from werkzeug.security import (
    generate_password_hash, 
    check_password_hash
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column, 
    Integer, 
    String
)

Base = declarative_base()

class DataEntry(Base):
    __tablename__ = 'data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String)
    imagepath = Column(String)
    posturl = Column(String)
    response = Column(String)
    embedding = Column(Vector(768))
    timestamp = Column(Integer)

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    created_at = Column(Integer)
    updated_at = Column(Integer)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
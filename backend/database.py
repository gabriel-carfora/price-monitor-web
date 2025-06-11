from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, TypeDecorator, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import os
import json
from datetime import datetime

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Custom JSON column type
class JSONType(TypeDecorator):
    """Enables JSON storage in SQLite."""
    impl = Text

    def process_bind_param(self, value, dialect):
        """Convert Python object to a JSON-encoded string."""
        if value is None:
            return '[]'
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        """Convert JSON-encoded string to Python object."""
        if value is None:
            return []
        return json.loads(value)

# Create SQLite database
DATABASE_URL = 'sqlite:///data/pricewatcher.db'
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocal = scoped_session(session_factory)

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    username = Column(String, primary_key=True, index=True)
    pushover_code = Column(String, nullable=True)
    price_limit = Column(Float, nullable=True)
    notification_frequency_days = Column(Integer, default=1)
    retailer_exclusions = Column(JSONType, default=list)

class Watchlist(Base):
    __tablename__ = 'watchlists'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    url = Column(String, index=True)

class PriceHistory(Base):
    __tablename__ = 'price_history'

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    retailer = Column(String)
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

class ProductDetails(Base):
    __tablename__ = 'product_details'

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    product_name = Column(String)
    best_price = Column(Float)
    average_price = Column(Float)
    lowest_price = Column(Float)
    highest_price = Column(Float)
    best_retailer = Column(String)
    price_variation = Column(Float)
    last_updated = Column(DateTime, default=datetime.utcnow)
    image_url = Column(String, nullable=True)
    retailers = Column(JSONType, default=list)
    price_history = Column(JSONType, default=list)

# Create tables
Base.metadata.create_all(bind=engine)

def get_db():
    """Create a database session"""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise
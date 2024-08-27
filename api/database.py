# api/database.py
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import Config

engine = create_engine(Config.POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Website(Base):
    __tablename__ = "websites"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    latest_version = Column(Integer, default=0)
    visits = relationship("Visit", back_populates="website")

class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey("websites.id"))
    timestamp = Column(DateTime, index=True)
    version = Column(Integer)
    content_hash = Column(String)
    cleaned_content = Column(Text)
    visit_metadata = Column(Text)  # Store as JSON

    website = relationship("Website", back_populates="visits")

Base.metadata.create_all(bind=engine)

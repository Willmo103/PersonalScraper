# api/database.py
from datetime import datetime
import uuid
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    Float,
    JSON,
    Table,
    Integer,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from config import Config

engine = create_engine(Config.POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Association tables
website_cookie = Table(
    "website_cookie",
    Base.metadata,
    Column(
        "website_id", UUID(as_uuid=True), ForeignKey("websites.id"), primary_key=True
    ),
    Column("cookie_id", UUID(as_uuid=True), ForeignKey("cookies.id"), primary_key=True),
)

website_topsite = Table(
    "website_topsite",
    Base.metadata,
    Column(
        "website_id", UUID(as_uuid=True), ForeignKey("websites.id"), primary_key=True
    ),
    Column(
        "topsite_id", UUID(as_uuid=True), ForeignKey("top_sites.id"), primary_key=True
    ),
)


class Website(Base):
    __tablename__ = "websites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    url = Column(String, unique=True, index=True)
    latest_version = Column(Integer, default=0)
    visits = relationship("Visit", back_populates="website")
    cookies = relationship(
        "Cookie", secondary=website_cookie, back_populates="websites"
    )
    top_sites = relationship(
        "TopSite", secondary=website_topsite, back_populates="websites"
    )


class Visit(Base):
    __tablename__ = "visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    website_id = Column(UUID(as_uuid=True), ForeignKey("websites.id"))
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)
    version = Column(Integer)
    content_hash = Column(String)
    cleaned_content = Column(Text)
    title = Column(String)

    is_bookmarked = Column(Boolean)
    idle_state = Column(String)

    website = relationship("Website", back_populates="visits")
    geolocation = relationship("Geolocation", uselist=False, back_populates="visit")


class Cookie(Base):
    __tablename__ = "cookies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String)
    domain = Column(String)
    path = Column(String)
    cookie_raw = Column(JSON)
    last_seen = Column(DateTime, default=datetime.utcnow)
    websites = relationship(
        "Website", secondary=website_cookie, back_populates="cookies"
    )


class Geolocation(Base):
    __tablename__ = "geolocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    visit_id = Column(UUID(as_uuid=True), ForeignKey("visits.id"), unique=True)
    latitude = Column(Float)
    longitude = Column(Float)

    visit = relationship("Visit", back_populates="geolocation")


class TopSite(Base):
    __tablename__ = "top_sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    url = Column(String, unique=True)
    title = Column(String)
    last_seen = Column(DateTime, default=datetime.utcnow)
    websites = relationship(
        "Website", secondary=website_topsite, back_populates="top_sites"
    )


class BrowsingHistory(Base):
    __tablename__ = "browsing_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    url = Column(String, index=True)
    title = Column(String)
    last_visit_time = Column(DateTime, index=True)
    visit_count = Column(Integer, default=1)


Base.metadata.create_all(bind=engine)

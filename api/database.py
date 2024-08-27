# api/database.py
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float, JSON, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import Config

engine = create_engine(Config.POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Association tables
website_cookie = Table('website_cookie', Base.metadata,
                       Column('website_id', Integer, ForeignKey('websites.id')),
                       Column('cookie_id', Integer, ForeignKey('cookies.id'))
                       )

website_topsite = Table('website_topsite', Base.metadata,
                        Column('website_id', Integer, ForeignKey('websites.id')),
                        Column('topsite_id', Integer, ForeignKey('top_sites.id'))
                        )


class Website(Base):
    __tablename__ = "websites"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    latest_version = Column(Integer, default=0)
    visits = relationship("Visit", back_populates="website")
    cookies = relationship("Cookie", secondary=website_cookie, back_populates="websites")
    top_sites = relationship("TopSite", secondary=website_topsite, back_populates="websites")


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey("websites.id"))
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

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    domain = Column(String)
    path = Column(String)
    last_seen = Column(DateTime, default=datetime.utcnow)
    websites = relationship("Website", secondary=website_cookie, back_populates="cookies")


class Geolocation(Base):
    __tablename__ = "geolocations"

    id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(Integer, ForeignKey("visits.id"), unique=True)
    latitude = Column(Float)
    longitude = Column(Float)

    visit = relationship("Visit", back_populates="geolocation")


class TopSite(Base):
    __tablename__ = "top_sites"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True)
    title = Column(String)
    last_seen = Column(DateTime, default=datetime.utcnow)
    websites = relationship("Website", secondary=website_topsite, back_populates="top_sites")


class BrowsingHistory(Base):
    __tablename__ = "browsing_history"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    title = Column(String)
    last_visit_time = Column(DateTime, index=True)
    visit_count = Column(Integer, default=1)


Base.metadata.create_all(bind=engine)
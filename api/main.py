# api/main.py
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import chromadb
from database import (
    SessionLocal,
    Website,
    Visit,
    BrowsingHistory,
    TopSite,
    Cookie,
    Geolocation,
)
from config import Config
from markdownify import markdownify as md

app = FastAPI()


# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Chroma client
chroma_client = chromadb.HttpClient(host=Config.CHROMA_HOST, port=Config.CHROMA_PORT)
collection = chroma_client.get_or_create_collection("web_history")


class VisitData(BaseModel):
    timestamp: str
    url: str
    title: str
    content: str
    contentHash: str
    version: int
    metadata: dict


def clean_content(content: str) -> str:
    markdown = md(content)
    return markdown


@app.post("/visit")
async def record_visit(visit_data: VisitData, db: Session = Depends(get_db)):
    # Check if website exists, if not create it
    website = db.query(Website).filter(Website.url == visit_data.url).first()
    if not website:
        website = Website(url=visit_data.url, latest_version=0)
        db.add(website)
        db.flush()

    # Clean the content
    cleaned_content = clean_content(visit_data.content)

    # Create new visit
    new_visit = Visit(
        website_id=website.id,
        timestamp=datetime.now(),
        version=visit_data.version,
        content_hash=visit_data.contentHash,
        cleaned_content=cleaned_content,
        title=visit_data.title,
        is_bookmarked=visit_data.metadata.get("isBookmarked", False),
        idle_state=visit_data.metadata.get("idleState", ""),
    )
    db.add(new_visit)
    db.flush()

    # Update or add geolocation
    geolocation = visit_data.metadata.get("geolocation")
    if geolocation:
        new_geolocation = Geolocation(
            visit_id=new_visit.id,
            latitude=geolocation.get("latitude"),
            longitude=geolocation.get("longitude"),
        )
        db.add(new_geolocation)

    # Update or add cookies
    for cookie_data in visit_data.metadata.get("cookies", []):
        cookie = (
            db.query(Cookie)
            .filter_by(name=cookie_data["name"], domain=cookie_data["domain"])
            .first()
        )
        if not cookie:
            cookie = Cookie(
                name=cookie_data["name"],
                domain=cookie_data["domain"],
                path=cookie_data["path"],
                cookie_raw=cookie_data,
            )
            db.add(cookie)
        cookie.last_seen = datetime.utcnow()
        if website not in cookie.websites:
            cookie.websites.append(website)

    # Update or add top sites
    for site in visit_data.metadata.get("topSites", []):
        top_site = db.query(TopSite).filter_by(url=site["url"]).first()
        if not top_site:
            top_site = TopSite(url=site["url"], title=site["title"])
            db.add(top_site)
        top_site.last_seen = datetime.utcnow()
        if website not in top_site.websites:
            top_site.websites.append(website)

    # Update browsing history
    for history_item in visit_data.metadata.get("recentHistory", []):
        history_entry = (
            db.query(BrowsingHistory).filter_by(url=history_item["url"]).first()
        )
        if history_entry:
            history_entry.visit_count += 1
            history_entry.last_visit_time = datetime.fromtimestamp(
                history_item["lastVisitTime"] / 1000
            )
        else:
            new_history = BrowsingHistory(
                url=history_item["url"],
                title=history_item["title"],
                last_visit_time=datetime.fromtimestamp(
                    history_item["lastVisitTime"] / 1000
                ),
                visit_count=1,
            )
            db.add(new_history)

    # Update website's latest version
    website.latest_version = max(website.latest_version, visit_data.version)

    db.commit()

    collection.add(
        documents=[cleaned_content],
        metadatas=[
            {
                "url": visit_data.url,
                "title": visit_data.title,
                "timestamp": datetime.timestamp(datetime.now()),
                "version": visit_data.version,
            }
        ],
        ids=[str(new_visit.id)],
    )

    return {
        "message": f"Successfully recorded visit for {visit_data.url} Version: {visit_data.version}"
    }


@app.get("/latest_version")
async def get_latest_version(url: str, db: Session = Depends(get_db)):
    website = db.query(Website).filter(Website.url == url).first()
    if website:
        return {"latest_version": website.latest_version}
    return {"latest_version": 0}


# Add more endpoints as needed for querying and analysis

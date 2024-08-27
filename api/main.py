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


@app.get("/visits")
async def get_visits(url: str, db: Session = Depends(get_db)):
    website = db.query(Website).filter(Website.url == url).first()
    if website:
        visits = db.query(Visit).filter(Visit.website_id == website.id).all()
        return {
            "url": url,
            "visits": [
                {
                    "timestamp": visit.timestamp,
                    "version": visit.version,
                    "title": visit.title,
                    "is_bookmarked": visit.is_bookmarked,
                    "idle_state": visit.idle_state,
                }
                for visit in visits
            ],
        }
    return {"message": f"No visits found for {url}"}


@app.get("/browsing_history")
async def get_browsing_history(
    url: str = None,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(BrowsingHistory)

    if url:
        query = query.filter(BrowsingHistory.url == url)

    if start_date:
        start_date = datetime.fromisoformat(start_date)
        query = query.filter(BrowsingHistory.last_visit_time >= start_date)

    if end_date:
        end_date = datetime.fromisoformat(end_date)
        query = query.filter(BrowsingHistory.last_visit_time <= end_date)

    history = query.all()

    return [
        {
            "url": item.url,
            "title": item.title,
            "last_visit_time": item.last_visit_time,
            "visit_count": item.visit_count,
        }
        for item in history
    ]


@app.get("/top_sites")
async def get_top_sites(db: Session = Depends(get_db)):
    top_sites = db.query(TopSite).all()
    return [
        {
            "url": site.url,
            "title": site.title,
            "last_seen": site.last_seen,
        }
        for site in top_sites
    ]


@app.get("/geolocation/{visit_id}")
async def get_geolocation(visit_id: int, db: Session = Depends(get_db)):
    geolocation = db.query(Geolocation).filter(Geolocation.visit_id == visit_id).first()
    if geolocation:
        return {
            "latitude": geolocation.latitude,
            "longitude": geolocation.longitude,
        }
    return {"message": "No geolocation data found for this visit"}


@app.get("/cookies")
async def get_cookies(url: str, db: Session = Depends(get_db)):
    website = db.query(Website).filter(Website.url == url).first()
    if website:
        cookies = (
            db.query(Cookie)
            .join(Cookie.websites)
            .filter(Website.id == website.id)
            .all()
        )
        return [
            {
                "name": cookie.name,
                "domain": cookie.domain,
                "path": cookie.path,
                "last_seen": cookie.last_seen,
                "cookie_raw": cookie.cookie_raw,
            }
            for cookie in cookies
        ]
    return {"message": f"No cookies found for {url}"}


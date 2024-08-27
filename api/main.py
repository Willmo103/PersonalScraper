# api/main.py
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import json
import chromadb
from database import SessionLocal, Website, Visit
from config import Config
from markdownify import markdownify as md
from bs4 import BeautifulSoup
import html2text

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
collection = chroma_client.get_or_create_collection("webtracker")

class VisitData(BaseModel):
    timestamp: str
    url: str
    title: str
    content: str
    contentHash: str
    version: int
    metadata: dict

def clean_content(content: str) -> str:
    # First, use BeautifulSoup to parse the HTML
    soup = BeautifulSoup(content, 'html.parser')

    # Remove all script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    # Get text
    text = soup.get_text()

    # Use html2text to convert to markdown
    h = html2text.HTML2Text()
    h.ignore_links = False
    markdown = h.handle(text)

    return markdown

@app.post("/visit")
async def record_visit(visit_data: VisitData, db: Session = Depends(get_db)):
    # Check if website exists, if not create it
    website = db.query(Website).filter(Website.url == visit_data.url).first()
    if not website:
        website = Website(url=visit_data.url, latest_version=0)
        db.add(website)
        db.commit()
        db.refresh(website)

    # Clean the content
    cleaned_content = clean_content(visit_data.content)

    # Check if content has changed
    existing_visit = db.query(Visit).filter(
        Visit.website_id == website.id,
        Visit.content_hash == visit_data.contentHash
    ).first()

    if existing_visit:
        return {"message": f"Content for {visit_data.url} hasn't changed"}

    # Process metadata
    processed_metadata = {
        "url": visit_data.url,
        "title": visit_data.title,
        "timestamp": datetime.timestamp(datetime.now()),
        "version": visit_data.version,
        "cookies": visit_data.metadata.get("cookies", []),
        "isBookmarked": visit_data.metadata.get("isBookmarked", False),
        "geolocation": visit_data.metadata.get("geolocation", {}),
        "topSites": visit_data.metadata.get("topSites", []),
        "idleState": visit_data.metadata.get("idleState", ""),
        "recentHistory": visit_data.metadata.get("recentHistory", [])
    }

    # Create new visit
    new_visit = Visit(
        website_id=website.id,
        timestamp=datetime.now(),
        version=visit_data.version,
        content_hash=visit_data.contentHash,
        cleaned_content=cleaned_content,
        visit_metadata=json.dumps(processed_metadata)
    )
    db.add(new_visit)

    # Update website's latest version
    website.latest_version = max(website.latest_version, visit_data.version)

    db.commit()
    db.refresh(new_visit)

    # Add to Chroma
    collection.add(
        documents=[cleaned_content],
        metadatas=[
            {
                "url": visit_data.url,
                "title": visit_data.title,
                "timestamp": datetime.timestamp(datetime.now()),
                "version": visit_data.version
            }
        ],
        ids=[str(new_visit.id)]
    )

    return {"message": f"Successfully recorded visit for {visit_data.url} Version: {visit_data.version}"}

@app.get("/latest_version")
async def get_latest_version(url: str, db: Session = Depends(get_db)):
    website = db.query(Website).filter(Website.url == url).first()
    if website:
        return {"latest_version": website.latest_version}
    return {"latest_version": 0}

# Add more endpoints as needed for querying and analysis

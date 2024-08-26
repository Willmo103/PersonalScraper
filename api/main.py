# api/main.py
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import json
import chromadb
from database import SessionLocal, Website, Visit
from config import Config

app = FastAPI()

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Chroma client
chroma_client = chromadb.Client(Config.CHROMA_HOST)
collection = chroma_client.create_collection("web_content")

class VisitData(BaseModel):
    timestamp: str
    url: str
    title: str
    content: str
    contentHash: str
    version: int
    metadata: dict

@app.post("/visit")
async def record_visit(visit_data: VisitData, db: Session = Depends(get_db)):
    # Check if website exists, if not create it
    website = db.query(Website).filter(Website.url == visit_data.url).first()
    if not website:
        website = Website(url=visit_data.url, latest_version=0)
        db.add(website)
        db.commit()
        db.refresh(website)

    # Check if content has changed
    existing_visit = db.query(Visit).filter(
        Visit.website_id == website.id,
        Visit.content_hash == visit_data.contentHash
    ).first()

    if existing_visit:
        return {"message": f"Content for {visit_data.url} hasn't changed"}

    # Create new visit
    new_visit = Visit(
        website_id=website.id,
        timestamp=datetime.fromisoformat(visit_data.timestamp),
        version=visit_data.version,
        content_hash=visit_data.contentHash,
        cleaned_content=visit_data.content,
        metadata=json.dumps(visit_data.metadata)
    )
    db.add(new_visit)

    # Update website's latest version
    website.latest_version = max(website.latest_version, visit_data.version)

    db.commit()
    db.refresh(new_visit)

    # Add to Chroma
    collection.add(
        documents=[visit_data.content],
        metadatas=[{
            "url": visit_data.url,
            "timestamp": visit_data.timestamp,
            "version": visit_data.version
        }],
        ids=[str(new_visit.id)]
    )

    return {"message": f"Successfully recorded visit for {visit_data.url}"}

@app.get("/latest_version")
async def get_latest_version(url: str, db: Session = Depends(get_db)):
    website = db.query(Website).filter(Website.url == url).first()
    if website:
        return {"latest_version": website.latest_version}
    return {"latest_version": 0}

# api/main.py
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import chromadb
from sentence_transformers import SentenceTransformer
import os
from bs4 import BeautifulSoup
import html2text
import yaml
from urllib.parse import urljoin
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize ChromaDB client
chroma_client = chromadb.HttpClient(host=os.getenv('CHROMA_HOST', 'localhost'), port=8000)
visit_collection = chroma_client.get_or_create_collection("website_visits")
static_collection = chroma_client.get_or_create_collection("static_data")

# Initialize sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Initialize HTML to Markdown converter
h = html2text.HTML2Text()
h.ignore_links = False

class VisitData(BaseModel):
    timestamp: str
    url: str
    title: str
    content: str
    contentHash: str
    version: int
    metadata: dict

class StaticData(BaseModel):
    timestamp: str
    type: str
    data: dict


@app.post("/visit")
async def record_visit(visit: VisitData):
    if not visit.content:
        raise HTTPException(status_code=400, detail="Empty content not allowed")

    try:
        # Check if this content hash already exists
        existing_visits = visit_collection.query(
            query_texts=[visit.contentHash],
            where={"$and": [{"url": visit.url}, {"contentHash": visit.contentHash}]},
            n_results=1
        )

        if existing_visits['ids']:
            logger.info(f"Content already exists for URL: {visit.url}")
            return {"status": "skipped", "message": "Content already exists"}

        # Process visit data
        metadata, markdown_content = clean_and_convert_to_markdown(visit.content, visit.url, visit.metadata)
        yaml_header = create_yaml_header(metadata)
        full_content = f"---\n{yaml_header}---\n\n{markdown_content}"

        # Store visit data
        embedding = model.encode(markdown_content).tolist()
        visit_collection.add(
            documents=[full_content],
            metadatas=[{
                "url": visit.url,
                "title": metadata.get("title", visit.title),
                "timestamp": visit.timestamp,
                "version": visit.version,
                "contentHash": visit.contentHash
            }],
            ids=[f"{visit.url}:{visit.version}"],
            embeddings=[embedding]
        )

        # Process static data
        await process_static_data(visit.metadata)

        logger.info(f"Visit recorded: {visit.url} (version {visit.version})")
        return {"status": "success", "message": "Visit recorded"}
    except Exception as e:
        logger.error(f"Error in record_visit: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing visit: {str(e)}")

async def process_static_data(metadata):
    timestamp = datetime.now().isoformat()

    # Process cookies
    if 'cookies' in metadata:
        static_collection.add(
            documents=[yaml.dump(metadata['cookies'])],
            metadatas=[{"type": "cookies", "timestamp": timestamp}],
            ids=[f"cookies:{timestamp}"]
        )

    # Process recent history
    if 'recentHistory' in metadata:
        static_collection.add(
            documents=[yaml.dump(metadata['recentHistory'])],
            metadatas=[{"type": "recentHistory", "timestamp": timestamp}],
            ids=[f"recentHistory:{timestamp}"]
        )

@app.get("/static-data/{data_type}")
async def get_static_data(data_type: str, start_time: str = None, end_time: str = None):
    try:
        where_clause = {"type": data_type}
        if start_time and end_time:
            where_clause["timestamp"] = {"$gte": start_time, "$lte": end_time}

        results = static_collection.query(
            query_texts=[""],
            where=where_clause,
            n_results=1000  # Adjust as needed
        )

        return [
            {
                "timestamp": meta["timestamp"],
                "data": yaml.safe_load(doc)
            }
            for meta, doc in zip(results["metadatas"], results["documents"])
        ]
    except Exception as e:
        logger.error(f"Error in get_static_data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving static data: {str(e)}")

@app.get("/visits")
async def get_visits(url: str, start_version: int = 0, end_version: int = None):
    try:
        where_clause = {"url": url}
        if end_version is not None:
            where_clause["version"] = {"$gte": start_version, "$lte": end_version}  # noqa
        else:
            where_clause["version"] = {"$gte": start_version}

        results = visit_collection.query(
            query_texts=[""],
            where=where_clause,
            n_results=1000  # Adjust as needed
        )

        visits = [
            {
                "version": meta["version"],
                "timestamp": meta["timestamp"],
                "contentHash": meta["contentHash"],
                "content": doc
            }
            for meta, doc in zip(results["metadatas"], results["documents"])
        ]

        visits.sort(key=lambda x: x['version'])
        return visits
    except Exception as e:
        logger.error(f"Error in get_visits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving visits: {str(e)}")

@app.get("/search")
async def search_visits(query: str, limit: int = 5):
    try:
        results = visit_collection.query(
            query_texts=[query],
            n_results=limit
        )
        return results
    except Exception as e:
        logger.error(f"Error in search_visits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error performing search: {str(e)}")

@app.get("/latest_version")
async def get_latest_version(url: str):
    try:
        results = visit_collection.query(
            query_texts=[""],
            where={"url": url},
            n_results=1,
            order_by={"version": "desc"}
        )
        if results['ids']:
            return {"url": url, "latest_version": results['metadatas'][0]['version']}
        else:
            return {"url": url, "latest_version": 0}
    except Exception as e:
        logger.error(f"Error in get_latest_version: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving latest version: {str(e)}")


@app.get("/chroma-stats")
async def get_chroma_stats():
    try:
        visit_count = len(visit_collection.get()['ids'])
        static_data_count = len(static_collection.get()['ids'])
        return {
            "visit_count": visit_count,
            "static_data_count": static_data_count
        }
    except Exception as e:
        logger.error(f"Error in get_chroma_stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving Chroma stats: {str(e)}")


def clean_and_convert_to_markdown(html_content, base_url, metadata):
    try:
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract links and images
        metadata["links"] = [urljoin(base_url, link['href']) for link in soup.find_all('a', href=True)]
        metadata["images"] = [urljoin(base_url, img['src']) for img in soup.find_all('img', src=True)]

        # Convert to Markdown
        markdown_content = h.handle(str(soup))

        return metadata, markdown_content
    except Exception as e:
        logger.error(f"Error in clean_and_convert_to_markdown: {str(e)}")
        raise

def create_yaml_header(metadata):
    return yaml.dump(metadata, default_flow_style=False)


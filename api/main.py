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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize ChromaDB client
chroma_client = chromadb.HttpClient(host=os.getenv('CHROMA_HOST', 'localhost'), port=8000)
collection = chroma_client.get_or_create_collection("website_visits")

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

@app.post("/visit")
async def record_visit(visit: VisitData):
    if not visit.content:
        raise HTTPException(status_code=400, detail="Empty content not allowed")

    try:
        # Check if this content hash already exists
        existing_visits = collection.query(
            query_texts=[visit.contentHash],
            where={"$and": [{"url": visit.url}, {"contentHash": visit.contentHash}]},
            n_results=1
        )

        if existing_visits['ids']:
            logger.info(f"Content already exists for URL: {visit.url}")
            return {"status": "skipped", "message": "Content already exists"}

        # Clean and convert content
        metadata, markdown_content = clean_and_convert_to_markdown(visit.content, visit.url, visit.metadata)

        # Create YAML header
        yaml_header = create_yaml_header(metadata)

        # Combine YAML header and Markdown content
        full_content = f"---\n{yaml_header}---\n\n{markdown_content}"

        # Embed and store in ChromaDB
        embedding = model.encode(markdown_content).tolist()
        collection.add(
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

        logger.info(f"Visit recorded: {visit.url} (version {visit.version})")
        return {"status": "success", "message": "Visit recorded"}
    except Exception as e:
        logger.error(f"Error in record_visit: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing visit: {str(e)}")

@app.get("/visits")
async def get_visits(url: str, start_version: int = 0, end_version: int = None):
    try:
        where_clause = {"url": url}
        if end_version is not None:
            where_clause["version"] = {"$gte": start_version, "$lte": end_version}
        else:
            where_clause["version"] = {"$gte": start_version}

        results = collection.query(
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
        results = collection.query(
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
        results = collection.query(
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
#!/usr/bin/env python3
"""
Main entry point for the search server application.
This script should be placed in /usr/local/bin/
"""

import os
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.templating import Jinja2Templates
import logging
from pathlib import Path

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

sys.pycache_prefix = "/var/cache/timebot/embedding_service"
from shared.config import config
from rag.search_utils import init_search_module

# Set up logging
logger = logging.getLogger()
log_file_path = config["EMBEDDING_SERVICE_LOG"]
log_directory = os.path.dirname(log_file_path)
Path(log_directory).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()  # Also log to console
    ]
)

# Lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Log application startup
    logger.info("Embedding service starting up")
    yield
    # Shutdown: Log application shutdown
    logger.info("Embedding service shutting down")

# Create FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="RAG Search API",
    description="API for searching emails, documents, and web content using Whoosh and ChromaDB"
)

# Add logging middleware
@app.middleware("http")
async def log_requests(request, call_next):
    """Log all incoming requests."""
    separator = "="*50
    logger.info(f"\n{separator}")
    logger.info(f"REQUEST: {request.method} {request.url.path}")

    # Log the client IP address
    client_host = request.client.host if request.client else "Unknown"
    logger.info(f"Client: {client_host}")

    # Log headers
    logger.info(f"Headers: {request.headers.get('content-type')}")

    # Log body
    try:
        body_bytes = await request.body()
        request._body = body_bytes  # Save the body for later use
        if body_bytes:
            try:
                body = body_bytes.decode()
                logger.info(f"Body: {body}")
            except:
                logger.info(f"Body: [binary data, length: {len(body_bytes)}]")
    except Exception as e:
        logger.error(f"Error reading body: {e}")

    logger.info(f"{separator}\n")

    response = await call_next(request)
    
    # Log response status code
    logger.info(f"Response status: {response.status_code}")
    
    return response

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Create a search configuration dictionary
search_config = {
    "SERVER_DIR": config["SERVER_DIR"],
    "DEFAULT_SIMILARITY_THRESHOLD": config["DEFAULT_SIMILARITY_THRESHOLD"],
    "DEFAULT_FUZZY_SEARCH": config["DEFAULT_FUZZY_SEARCH"],
    "USE_RERANKING": config["USE_RERANKING"],
    "EMBEDDING_MODEL": config["EMBEDDING_MODEL"],
    "RERANKER_MODEL": config["RERANKER_MODEL"],
    "CHROMADB_EMAIL_COLLECTION": config["CHROMADB_EMAIL_COLLECTION"],
    "CHROMADB_DOC_COLLECTION": config["CHROMADB_DOC_COLLECTION"],
    "CHROMADB_WEB_COLLECTION": config["CHROMADB_WEB_COLLECTION"],  # Added web collection
    "CHROMADB_PATH": config["CHROMADB_PATH"],
    "WHOOSHDB_EMAIL_PATH": config["WHOOSHDB_EMAIL_PATH"],
    "WHOOSHDB_DOC_PATH": config["WHOOSHDB_DOC_PATH"],
    "WHOOSHDB_WEB_PATH": config["WHOOSHDB_WEB_PATH"],  # Added web path
    "TOP_K": config["TOP_K"],
    "HOST": config["EMBEDDING_SERVER_LISTEN_ADDR"],
    "PORT": config["EMBEDDING_SERVER_PORT"],
    # Collection weights
    "DOCUMENT_COLLECTION_WEIGHT": config["DOCUMENT_COLLECTION_WEIGHT"],
    "EMAIL_COLLECTION_WEIGHT": config["EMAIL_COLLECTION_WEIGHT"],
    "WEB_COLLECTION_WEIGHT": config["WEB_COLLECTION_WEIGHT"],  # Added web weight
    "RECENCY_WEIGHT": config["RECENCY_WEIGHT"],
    "RECENCY_DECAY_DAYS": config["RECENCY_DECAY_DAYS"],
    "CHROMADB_WEIGHT": config["CHROMADB_WEIGHT"],
    "WHOOSH_WEIGHT": config["WHOOSH_WEIGHT"],
    "RERANKER_WEIGHT": config["RERANKER_WEIGHT"],
    "USE_WEIGHTING": config["USE_WEIGHTING"],
    "SIMILARITY_THRESHOLD": config["SIMILARITY_THRESHOLD"],
}

SERVER_DIR = search_config["SERVER_DIR"]
# Mount static files directory
app.mount("/static",
    StaticFiles(directory=os.path.join(SERVER_DIR, "static")), name="static")

# Initialize the search module with our app and config
logger.info("Initializing search module")
init_search_module(app, search_config)
logger.info("Search module initialized successfully")

if __name__ == "__main__":
    logger.info(f"Starting server with SERVER_DIR: {SERVER_DIR}")
    logger.info(f"Server will listen on {search_config['HOST']}:{search_config['PORT']}")
    uvicorn.run(
        "embedding_service:app",
        host=search_config["HOST"],
        port=search_config["PORT"],
    )


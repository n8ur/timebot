# /usr/local/lib/timebot/lib/rag/api_routes.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

"""
API routes for search functionality.
"""

import logging

from fastapi import APIRouter, Body, Request, HTTPException
from fastapi.responses import HTMLResponse

from .models import QueryRequest
from .api_handlers import handle_api_query, handle_metadata_search

# set up logger
logger = logging.getLogger(__name__)
# Create router for API endpoints
router = APIRouter()

@router.get("/info")
async def api_info(request: Request):
    """Return information about the API."""
    # Get config from request.app.state
    config = getattr(request.app.state, "config", {})
    
    return {
        "name": "RAG Search API",
        "version": "1.0.0",
        "description": "API for searching emails, documents, and web content using Whoosh and ChromaDB",
        "models": {
            "embedding": config["EMBEDDING_MODEL"],
            "reranking": config["RERANKER_MODEL"],
        },
        "collections": ["emails", "documents", "web"]
    }

@router.post("/query")
async def api_query(request: Request, query_request: QueryRequest = Body(...)):
    """API endpoint for querying the search system."""
    config = getattr(request.app.state, "config", {})
    return await handle_api_query(query_request, config)

@router.post("/metadata_search")
async def api_metadata_search(request: Request, metadata_request: dict):
    """API endpoint for searching by metadata."""
    metadata = metadata_request.get("metadata", {})
    if not metadata:
        raise HTTPException(status_code=400, detail="No metadata queries provided")
    
    content_query = metadata_request.get("query", "")
    top_k = metadata_request.get("top_k", 100)
    metadata_fuzzy = metadata_request.get("metadata_fuzzy", True)
    metadata_threshold = metadata_request.get("metadata_threshold", 0.8)
    collection_filter = metadata_request.get("collection_filter", "all")
    
    # Get config from app state
    config = getattr(request.app.state, "config", {})
    
    # Use the new handler function
    return await handle_metadata_search(
        metadata=metadata,
        content_query=content_query,
        top_k=top_k,
        metadata_fuzzy=metadata_fuzzy,
        metadata_threshold=metadata_threshold,
        collection_filter=collection_filter,
        config=config
    )

@router.get("/docs", response_class=HTMLResponse)
async def api_docs(request: Request):
    """Render API documentation."""
    # Get templates from request.app.state
    templates = getattr(request.app.state, "templates", None)
    if not templates:
        raise HTTPException(status_code=500, detail="Templates not configured")
    
    return templates.TemplateResponse(
        "api_docs.html",
        {
            "request": request,
            "api_base_url": request.base_url
        }
    )

@router.get("/test", response_class=HTMLResponse)
async def api_test_page(request: Request):
    """Render API test page."""
    # Get templates from request.app.state
    templates = getattr(request.app.state, "templates", None)
    if not templates:
        raise HTTPException(status_code=500, detail="Templates not configured")
    
    return templates.TemplateResponse(
        "api_test.html",
        {
            "request": request
        }
    )


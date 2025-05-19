# /usr/local/lib/timebot/lib/rag/search_utils.py

"""
Search utilities for the RAG application.
This file provides the main interface for the search functionality.
"""

import os
from fastapi.templating import Jinja2Templates

# Import the main search function
from rag.search_logic import perform_search_logic

# Import the routers
from rag.api_routes import router

# Function to initialize the module with the main application
def init_search_module(app, config):
    """Initialize the search module with the FastAPI app and configuration."""
    # Store config in app.state for access in route handlers
    app.state.config = config
    
    # Set up templates
    templates_dir = os.path.join(config["SERVER_DIR"], "templates/rag")
    app.state.templates = Jinja2Templates(directory=templates_dir)
    
    # Include routers
    app.include_router(router, prefix="/api")
    
    return app

# Define search_documents as an alias for perform_search_logic
# This ensures backward compatibility if any code is directly calling search_documents
search_documents = perform_search_logic


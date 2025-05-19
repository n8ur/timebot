# Import everything from the split modules to maintain backward compatibility
from .chromadb_core import db_manager, close_collection
from .chromadb_collections import (
    open_collection, open_existing_collection, document_exists,
    add_document, add_documents_batch, initialize_chromadb, ingest_to_chromadb
)
from .chromadb_search import (
    search_emails, search_documents, search_web,
    search_emails_unified, search_documents_unified, search_web_unified
)


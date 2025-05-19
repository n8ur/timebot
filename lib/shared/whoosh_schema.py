# whoosh_schema.py

from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.analysis import StemmingAnalyzer

def define_whoosh_schema(schema_type: str = "email") -> Schema:
    """
    Define Whoosh schema with metadata and full-text search fields.

    Args:
        schema_type: The type of schema to create (e.g., "email", "document", "web")

    Returns:
        A Whoosh Schema object configured for the specified document type
    """
    if schema_type == "email":
        return Schema(
            doc_id=ID(stored=True),  # Unique ID (hash)
            from_=TEXT(stored=True),  # 'from' is a reserved keyword, using 'from_' instead
            date=TEXT(stored=True),
            subject=TEXT(stored=True),
            url=ID(stored=True),  # URL for reference
            content=TEXT(stored=True, analyzer=StemmingAnalyzer()),  # Full-text searchable content
        )
    elif schema_type == "document":
        # Example for a different collection type
        return Schema(
            doc_id=ID(stored=True),
            title=TEXT(stored=True),
            author=TEXT(stored=True),
            date=TEXT(stored=True),
            content=TEXT(stored=True, analyzer=StemmingAnalyzer()),
        )
    elif schema_type == "web":
        # Schema for web documents
        return Schema(
            doc_id=ID(stored=True),  # Unique ID (hash)
            source_url=ID(stored=True),  # Original URL of the web page
            title=TEXT(stored=True),  # Title of the web page
            captured_at=TEXT(stored=True),  # Timestamp when the page was captured
            domain=TEXT(stored=True),  # Extracted domain from source_url (for filtering)
            content=TEXT(stored=True, analyzer=StemmingAnalyzer()),  # Full-text searchable content
        )
    elif schema_type == "technical":
        return Schema(
            doc_id=ID(stored=True),  # Unique ID (hash)
            title=TEXT(stored=True),
            author=TEXT(stored=True),
            publisher=TEXT(stored=True),
            publisher_id=TEXT(stored=True),
            publication_date=TEXT(stored=True),
            source=TEXT(stored=True),
            sequence_number=TEXT(stored=True),
            url=ID(stored=True),
            processing_date=TEXT(stored=True),
            content=TEXT(stored=True, analyzer=StemmingAnalyzer()),
            is_chunk=STORED,  # Boolean to indicate if this is a chunk
            chunk_number=STORED,  # If chunked, which chunk number
            total_chunks=STORED,  # Total number of chunks
            parent_hash=ID(stored=True),  # Hash of the parent document if this is a chunk
            chunk_id=ID(stored=True),  # Unique identifier for the chunk
        )
    else:
        # Default schema with minimal fields
        return Schema(
            doc_id=ID(stored=True),
            content=TEXT(stored=True, analyzer=StemmingAnalyzer()),
        )


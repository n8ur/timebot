# whoosh_document.py

from typing import Dict, Any, Optional, List
from whoosh.index import open_dir
from .email_parser import parse_email_message  # Add this import

def document_exists_in_whoosh(index, doc_id: str) -> bool:
    """
    Check if a document with the given ID exists in the Whoosh index.

    Args:
        index: Whoosh index object
        doc_id: Document ID to check

    Returns:
        True if document exists, False otherwise
    """
    try:
        with index.searcher() as searcher:
            return searcher.document(doc_id=doc_id) is not None
    except Exception as e:
        print(f"Error checking document existence in Whoosh: {e}")
        return False


def add_document_to_whoosh(
    writer,
    chunk_text: str,
    metadata: Dict[str, Any],
    schema_type: str = "email",
    verbose: bool = False,
) -> None:
    """
    Add a document to the Whoosh index based on schema type.

    Args:
        writer: Whoosh index writer
        chunk_text: The text content of the chunk
        metadata: Document metadata (excluding content)
        schema_type: Type of schema being used
        verbose: Whether to print verbose output
    """
    try:
        if schema_type == "email":
            # Email schema handling (unchanged)
            if "raw_message" in metadata:
                parsed_metadata, parsed_content = parse_email_message(metadata["raw_message"])
                # Use parsed content if chunk_text is empty or not provided
                if not chunk_text.strip():
                    chunk_text = parsed_content
                
                # Add document with properly parsed metadata
                writer.add_document(
                    doc_id=metadata["hash"],
                    from_=parsed_metadata["from_"],
                    date=parsed_metadata["date"],
                    subject=parsed_metadata["subject"],
                    url=parsed_metadata["url"],
                    content=chunk_text,
                )
            else:
                # Use provided metadata if raw_message is not available
                writer.add_document(
                    doc_id=metadata["hash"],
                    from_=metadata.get("from_", "Unknown"),
                    date=metadata.get("date", "Unknown"),
                    subject=metadata.get("subject", "Unknown"),
                    url=metadata.get("url", ""),
                    content=chunk_text,
                )
        elif schema_type == "technical":
            # Technical schema handling (unchanged)
            doc = {
                "doc_id": metadata["hash"],
                "content": chunk_text,
                "title": metadata.get("title", "Unknown"),
                "author": metadata.get("author", "Unknown"),
                "publisher": metadata.get("publisher", "Unknown"),
                "publisher_id": metadata.get("publisher_id", "Unknown"),
                "publication_date": metadata.get("publication_date", "Unknown"),
                "source": metadata.get("source", "Unknown"),
                "sequence_number": metadata.get("sequence_number", "Unknown"),
                "url": metadata.get("url", "Unknown"),
                "processing_date": metadata.get("processing_date", "Unknown"),
                "is_chunk": metadata.get("is_chunk", False),
                "chunk_number": metadata.get("chunk_number", 0),
                "total_chunks": metadata.get("total_chunks", 0),
                "parent_hash": metadata.get("parent_hash", ""),
                "chunk_id": metadata.get("chunk_id", ""),
            }
            writer.add_document(**doc)
        elif schema_type == "web":
            # Add specific case for web schema
            doc = {
                "doc_id": metadata["hash"],
                "source_url": metadata.get("source_url", ""),
                "title": metadata.get("title", "Unknown"),
                "captured_at": metadata.get("captured_at", ""),
                "domain": metadata.get("domain", ""),
                "content": chunk_text
            }
            writer.add_document(**doc)
        else:
            writer.add_document(doc_id=metadata["hash"], content=chunk_text)

        if verbose:
            print(
                f"✅ Ingested into Whoosh: {metadata.get('url', metadata.get('file_name', 'Unknown'))}"
            )
    except Exception as e:
        print(f"Error adding document to Whoosh: {e}")



def get_document_by_id(index_dir: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a document by its ID.

    Args:
        index_dir: Directory path for the Whoosh index
        doc_id: Document ID to retrieve

    Returns:
        Document as a dictionary or None if not found
    """
    ix = open_dir(index_dir)

    with ix.searcher() as searcher:
        doc = searcher.document(doc_id=doc_id)
        if doc:
            return dict(doc)

    return None


def get_all_documents(index_dir: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Retrieve all documents from the index up to the specified limit.

    Args:
        index_dir: Directory path for the Whoosh index
        limit: Maximum number of documents to retrieve

    Returns:
        List of documents as dictionaries
    """
    ix = open_dir(index_dir)
    results = []

    with ix.searcher() as searcher:
        # Get all documents (up to the limit)
        all_docs = searcher.documents(limit=limit)
        
        for doc in all_docs:
            results.append(dict(doc))
            
    return results


def delete_document(index_dir: str, doc_id: str) -> bool:
    """
    Delete a document from the index by its ID.

    Args:
        index_dir: Directory path for the Whoosh index
        doc_id: Document ID to delete

    Returns:
        True if document was deleted, False otherwise
    """
    ix = open_dir(index_dir)
    
    try:
        writer = ix.writer()
        writer.delete_by_term('doc_id', doc_id)
        writer.commit()
        return True
    except Exception as e:
        print(f"Error deleting document from Whoosh: {e}")
        return False


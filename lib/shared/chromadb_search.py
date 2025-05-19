# chromadb_search.py

from typing import List, Dict, Any, Optional
from datetime import datetime

from .chromadb_core import db_manager
from .search_result import SearchResult

verbose=False

def search_emails(
    collection_name: str,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.0,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    Search the email collection with the given query.
    
    Args:
        collection_name: Name of the collection to search
        query: The search query
        limit: Maximum number of results to return
        similarity_threshold: Minimum similarity score (0-1) for results
        verbose: Whether to print verbose output
        
    Returns:
        List of search results with standardized format
        
    Raises:
        ValueError: If the collection doesn't exist or isn't opened
    """
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened. Please open it first.")
    
    collection = db_manager.contexts[collection_name].collection
    
    if verbose:
        print(f"Searching ChromaDB email collection '{collection_name}' for: '{query}'")
    
    # Query the collection
    results = collection.query(
        query_texts=[query],
        n_results=limit,
        include=["documents", "metadatas", "distances"]
    )
    
    processed_results = []
    
    # Process results if we got any
    if results["documents"] and len(results["documents"][0]) > 0:
        for i in range(len(results["documents"][0])):
            # Convert distance to similarity score (ChromaDB returns distances, lower is better)
            similarity = 1.0 - float(results["distances"][0][i])
            
            # Skip results below threshold
            if similarity < similarity_threshold:
                continue
            
            # Extract metadata, handling both "from_" and "from" fields
            metadata = results["metadatas"][0][i]
            
            processed_results.append({
                "score": similarity,
                "from": metadata.get("from_", metadata.get("from", "Unknown")),
                "date": metadata.get("date", "Unknown"),
                "subject": metadata.get("subject", "Unknown"),
                "url": metadata.get("url", "Unknown"),
                "message": results["documents"][0][i],
                "content": results["documents"][0][i],
                "search_provider": "ChromaDB-Email",
                "id": metadata.get("hash", metadata.get("url", f"chroma-email-{i}"))
            })
    
    if verbose:
        print(f"Found {len(processed_results)} email results within threshold")
    
    return processed_results


def search_documents(
    collection_name: str,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.0,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    Search the documents collection with the given query.
    
    Args:
        collection_name: Name of the collection to search
        query: The search query
        limit: Maximum number of results to return
        similarity_threshold: Minimum similarity score (0-1) for results
        verbose: Whether to print verbose output
        
    Returns:
        List of search results with standardized format
        
    Raises:
        ValueError: If the collection doesn't exist or isn't opened
    """
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened. Please open it first.")
    
    collection = db_manager.contexts[collection_name].collection
    
    if verbose:
        print(f"Searching ChromaDB document collection '{collection_name}' for: '{query}'")
    
    # Query the collection
    results = collection.query(
        query_texts=[query],
        n_results=limit,
        include=["documents", "metadatas", "distances"]
    )
    
    processed_results = []
    
    # Process results if we got any
    if results["documents"] and len(results["documents"][0]) > 0:
        for i in range(len(results["documents"][0])):
            # Convert distance to similarity score (ChromaDB returns distances, lower is better)
            similarity = 1.0 - float(results["distances"][0][i])
            
            # Skip results below threshold
            if similarity < similarity_threshold:
                continue
            
            # Extract metadata
            metadata = results["metadatas"][0][i]
            
            processed_results.append({
                "score": similarity,
                "title": metadata.get("title", "Unknown"),
                "author": metadata.get("author", "Unknown"),
                "publication_date": metadata.get("publication_date", "Unknown"),
                "url": metadata.get("url", "Unknown"),
                "message": results["documents"][0][i],
                "content": results["documents"][0][i],
                "search_provider": "ChromaDB-Document",
                "id": metadata.get("hash", metadata.get("url", f"chroma-doc-{i}"))
            })
    
    if verbose:
        print(f"Found {len(processed_results)} document results within threshold")
    
    return processed_results


def search_emails_unified(
    collection_name: str,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.0,
    verbose: bool = False
) -> List[SearchResult]:
    """
    Search the email collection with the given query and return unified SearchResult objects.
    
    Args:
        collection_name: Name of the collection to search
        query: The search query
        limit: Maximum number of results to return
        similarity_threshold: Minimum similarity score (0-1) for results
        verbose: Whether to print verbose output
        
    Returns:
        List of SearchResult objects
        
    Raises:
        ValueError: If the collection doesn't exist or isn't opened
    """
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened. Please open it first.")
    
    collection = db_manager.contexts[collection_name].collection
    
    if verbose:
        print(f"Searching ChromaDB email collection '{collection_name}' for: '{query}'")
    
    # Query the collection
    results = collection.query(
        query_texts=[query],
        n_results=limit,
        include=["documents", "metadatas", "distances"]
    )
    
    search_results = []
    
    # Process results if we got any
    if results["documents"] and len(results["documents"][0]) > 0:
        for i in range(len(results["documents"][0])):
            # Convert distance to similarity score (ChromaDB returns distances, lower is better)
            similarity = 1.0 - results["distances"][0][i]
            
            # Skip results below threshold
            if similarity < similarity_threshold:
                continue
            
            # Extract metadata
            metadata = results["metadatas"][0][i]
            doc_id = metadata.get("hash", metadata.get("url", f"chroma-email-{i}"))
            
            # Create a SearchResult object using the factory method
            search_result = SearchResult.from_chroma_email({
                "id": doc_id,
                "text": results["documents"][0][i],
                "score": similarity,
                "metadata": metadata
            })
            
            search_results.append(search_result)
    
    if verbose:
        print(f"Found {len(search_results)} email results within threshold")
    
    return search_results


def search_documents_unified(
    collection_name: str,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.0,
    verbose: bool = False
) -> List[SearchResult]:
    """
    Search the documents collection with the given query and return unified SearchResult objects.
    
    Args:
        collection_name: Name of the collection to search
        query: The search query
        limit: Maximum number of results to return
        similarity_threshold: Minimum similarity score (0-1) for results
        verbose: Whether to print verbose output
        
    Returns:
        List of SearchResult objects
        
    Raises:
        ValueError: If the collection doesn't exist or isn't opened
    """
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened. Please open it first.")
    
    collection = db_manager.contexts[collection_name].collection
    
    if verbose:
        print(f"Searching ChromaDB document collection '{collection_name}' for: '{query}'")
    
    # Query the collection
    results = collection.query(
        query_texts=[query],
        n_results=limit,
        include=["documents", "metadatas", "distances"]
    )
    
    search_results = []
    
    # Process results if we got any
    if results["documents"] and len(results["documents"][0]) > 0:
        for i in range(len(results["documents"][0])):
            # Convert distance to similarity score (ChromaDB returns distances, lower is better)
            similarity = 1.0 - results["distances"][0][i]
            
            # Skip results below threshold
            if similarity < similarity_threshold:
                continue
            
            # Extract metadata
            metadata = results["metadatas"][0][i]
            doc_id = metadata.get("hash", metadata.get("url", f"chroma-doc-{i}"))
            
            # Create a SearchResult object using the factory method
            search_result = SearchResult.from_chroma_document({
                "id": doc_id,
                "text": results["documents"][0][i],
                "score": similarity,
                "metadata": metadata
            })
            
            search_results.append(search_result)
    
    if verbose:
        print(f"Found {len(search_results)} document results within threshold")
    
    return search_results

def search_web(
    collection_name: str,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.0,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    Search the web collection with the given query.

    Args:
        collection_name: Name of the collection to search
        query: The search query
        limit: Maximum number of results to return
        similarity_threshold: Minimum similarity score (0-1) for results
        verbose: Whether to print verbose output

    Returns:
        List of search results with standardized format

    Raises:
        ValueError: If the collection doesn't exist or isn't opened
    """
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened. Please open it first.")

    collection = db_manager.contexts[collection_name].collection

    if verbose:
        print(f"Searching ChromaDB web collection '{collection_name}' for: '{query}'")

    # Query the collection
    results = collection.query(
        query_texts=[query],
        n_results=limit,
        include=["documents", "metadatas", "distances"]
    )

    processed_results = []

    # Process results if we got any
    if results["documents"] and len(results["documents"][0]) > 0:
        for i in range(len(results["documents"][0])):
            # Convert distance to similarity score (ChromaDB returns distances, lower is better)
            similarity = 1.0 - float(results["distances"][0][i])

            # Skip results below threshold
            if similarity < similarity_threshold:
                continue

            # Extract metadata
            metadata = results["metadatas"][0][i]

            processed_results.append({
                "score": similarity,
                "title": metadata.get("title", "Unknown"),
                "source_url": metadata.get("source_url", "Unknown"),
                "captured_at": metadata.get("captured_at", "Unknown"),
                "domain": metadata.get("domain", "Unknown"),
                "message": results["documents"][0][i],
                "content": results["documents"][0][i],
                "search_provider": "ChromaDB-Web",
                "id": metadata.get("hash", metadata.get("source_url", f"chroma-web-{i}"))
            })

    if verbose:
        print(f"Found {len(processed_results)} web results within threshold")

    return processed_results


def search_web_unified(
    collection_name: str,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.0,
    verbose: bool = False
) -> List[SearchResult]:
    """
    Search the web collection with the given query and return unified SearchResult objects.

    Args:
        collection_name: Name of the collection to search
        query: The search query
        limit: Maximum number of results to return
        similarity_threshold: Minimum similarity score (0-1) for results
        verbose: Whether to print verbose output

    Returns:
        List of SearchResult objects

    Raises:
        ValueError: If the collection doesn't exist or isn't opened
    """
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened. Please open it first.")

    collection = db_manager.contexts[collection_name].collection

    if verbose:
        print(f"Searching ChromaDB web collection '{collection_name}' for: '{query}'")

    # Query the collection
    results = collection.query(
        query_texts=[query],
        n_results=limit,
        include=["documents", "metadatas", "distances"]
    )

    search_results = []

    # Process results if we got any
    if results["documents"] and len(results["documents"][0]) > 0:
        for i in range(len(results["documents"][0])):
            # Convert distance to similarity score (ChromaDB returns distances, lower is better)
            similarity = 1.0 - results["distances"][0][i]

            # Skip results below threshold
            if similarity < similarity_threshold:
                continue

            # Extract metadata
            metadata = results["metadatas"][0][i]
            doc_id = metadata.get("hash", metadata.get("source_url", f"chroma-web-{i}"))

            # Create a SearchResult object using the factory method
            search_result = SearchResult.from_chroma_web({
                "id": doc_id,
                "text": results["documents"][0][i],
                "score": similarity,
                "metadata": metadata
            })

            search_results.append(search_result)

    if verbose:
        print(f"Found {len(search_results)} web results within threshold")

    return search_results


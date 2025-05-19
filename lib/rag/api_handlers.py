# /usr/local/lib/timebot/lib/rag/api_handlers.py

"""
API request handlers for search functionality.
"""

from fastapi import HTTPException
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

from .models import QueryRequest, QueryResponse, Document, WeightConfig
from .search_logic import perform_search_logic

def format_search_results(results: List[Dict[str, Any]]) -> List[Document]:
    """Format search results into Document objects for API responses.
    
    Args:
        results: List of raw search results
        
    Returns:
        List of Document objects
    """
    formatted_results = []
    for result in results:
        # Get the "from" field with fallback
        from_value = result.get("from") or result.get("from_", "Unknown")

        # Create comprehensive metadata dictionary
        metadata = {
            "doc_type": result.get("doc_type", "unknown"),
            "from": from_value,
            "date": result.get("date", "Unknown"),
            "subject": result.get("subject", "Unknown"),
            "url": result.get("url", "Unknown"),
            "source": result.get("source", "Unknown"),
            "search_provider": result.get("search_provider", "Unknown")  # Explicitly include search provider
        }

        # Add document-specific fields if present
        if result.get("doc_type") == "document":
            metadata["title"] = result.get("title", "Untitled Document")
            metadata["author"] = result.get("author", "Unknown Author")
            metadata["publisher"] = result.get("publisher", "Unknown Publisher")
            metadata["publisher_id"] = result.get("publisher_id", "")  # Include publisher_id

            # Add chunk information for documents
            metadata["chunk_number"] = result.get("chunk_number", 1)
            metadata["total_chunks"] = result.get("total_chunks", 1)
        elif result.get("doc_type") == "email":
            # For emails, use 1 for both chunk values
            metadata["chunk_number"] = 1
            metadata["total_chunks"] = 1
        elif result.get("doc_type") == "web" or (result.get("doc_type") == "unknown" and (result.get("source_url") or result.get("domain"))):
            # Add web-specific fields
            metadata["title"] = result.get("title", "Untitled Web Page")
            metadata["source_url"] = result.get("source_url", "")
            metadata["captured_at"] = result.get("captured_at", "")
            metadata["domain"] = result.get("domain", "")
            # For web documents, use 1 for both chunk values
            metadata["chunk_number"] = 1
            metadata["total_chunks"] = 1
            
            # If doc_type is unknown but has web-specific fields, set it to "web"
            if result.get("doc_type") == "unknown":
                metadata["doc_type"] = "web"

        # Add reranking score if available
        if "rerank_score" in result:
            metadata["rerank_score"] = result["rerank_score"]
            metadata["original_score"] = result["original_score"]

        # Add weighting information if available in the result
        weighting_fields = [
            "original_score", "collection_weight", "recency_score", 
            "recency_factor", "source_weight", "final_score", 
            "diversity_adjustment", "business_score"
        ]
        
        weighting_info = {}
        for field in weighting_fields:
            if field in result:
                weighting_info[field] = result[field]
                
        if weighting_info:
            metadata["weighting"] = weighting_info

        # Add metadata match information if available
        if "metadata_matches" in result:
            metadata["metadata_matches"] = result["metadata_matches"]
        if "metadata_score" in result:
            metadata["metadata_score"] = result["metadata_score"]

        # Include any other fields that might be in the result
        for key, value in result.items():
            if key not in ["id", "content", "message", "score"] and key not in metadata:
                metadata[key] = value

        # Create document object
        doc = Document(
            id=result.get("id", f"result-{len(formatted_results)}"),
            content=result.get("content", result.get("message", "")),
            metadata=metadata,
            score=result.get("score", 0.0)
        )
        formatted_results.append(doc)
    
    return formatted_results


async def handle_api_query(request_data: QueryRequest, config: Dict[str, Any] = None):
    """Handle API query requests.

    Args:
        request_data: QueryRequest object
        config: Configuration dictionary

    Returns:
        QueryResponse object
    """
    try:
        # Create a copy of the config to avoid modifying the original
        config_copy = config.copy() if config else {}

        # Extract weight parameters if provided
        if hasattr(request_data, 'weights') and request_data.weights:
            weights_dict = request_data.weights.model_dump(exclude_none=True)
            for key, value in weights_dict.items():
                config_key = key.upper()
                config_copy[config_key] = value

        # Extract metadata queries if provided
        metadata_queries = None
        if hasattr(request_data, 'metadata') and request_data.metadata:
            metadata_dict = request_data.metadata.model_dump(exclude_none=True, by_alias=True)
            if metadata_dict:
                metadata_queries = metadata_dict
                logger.info(f"Metadata queries extracted: {metadata_queries}")

        results = perform_search_logic(
            query=request_data.query,
            mode=request_data.mode,
            fuzzy=request_data.fuzzy,
            similarity_threshold=request_data.similarity_threshold,
            use_reranking=request_data.use_reranking,
            top_k=request_data.top_k,
            collection_filter=request_data.collection_filter,
            metadata_queries=metadata_queries,
            metadata_fuzzy=request_data.metadata_fuzzy,
            metadata_threshold=request_data.metadata_threshold,
            config=config_copy
        )

        # Format results for the API response using the shared function
        formatted_results = format_search_results(results)

        # Create response
        response = QueryResponse(
            query=request_data.query,
            results=formatted_results
        )

        # Add weights information if weighting was applied
        if config_copy.get("USE_WEIGHTING", False) and hasattr(response, 'weights'):
            response.weights = WeightConfig(
                document_collection_weight=config_copy.get("DOCUMENT_COLLECTION_WEIGHT"),
                email_collection_weight=config_copy.get("EMAIL_COLLECTION_WEIGHT"),
                web_collection_weight=config_copy.get("WEB_COLLECTION_WEIGHT"),
                recency_weight=config_copy.get("RECENCY_WEIGHT"),
                recency_decay_days=config_copy.get("RECENCY_DECAY_DAYS"),
                chromadb_weight=config_copy.get("CHROMADB_WEIGHT"),
                whoosh_weight=config_copy.get("WHOOSH_WEIGHT"),
                reranker_weight=config_copy.get("RERANKER_WEIGHT")
            )

        return response
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

async def handle_metadata_search(metadata: Dict[str, Any], content_query: str, 
                                top_k: int, metadata_fuzzy: bool, 
                                metadata_threshold: float, collection_filter: str, 
                                config: Dict[str, Any] = None):
    """Handle metadata search requests.
    
    Args:
        metadata: Dictionary of metadata queries
        content_query: Optional content query string
        top_k: Maximum number of results to return
        metadata_fuzzy: Whether to use fuzzy matching for metadata
        metadata_threshold: Similarity threshold for metadata matching
        collection_filter: Filter for collections ("all", "emails", "documents", "web")
        config: Configuration dictionary
        
    Returns:
        QueryResponse object
    """
    try:
        # Get config from app state
        config_copy = config.copy() if config else {}
        
        # Use the Whoosh metadata search function
        from .metadata_search import search_by_whoosh_metadata
        
        results = search_by_whoosh_metadata(
            metadata_queries=metadata,
            content_query=content_query,
            fuzzy=metadata_fuzzy,
            top_k=top_k,
            collection_filter=collection_filter,
            config=config_copy
        )
        
        # If no results from Whoosh search and content query exists, try regular
        # search with metadata filtering through the search_logic
        if not results and content_query:
            logger.info("No results from Whoosh metadata search, falling back to regular search")
            from .search_logic import perform_search_logic
            
            # Perform regular search with metadata queries
            results = perform_search_logic(
                query=content_query,
                mode="combined",
                fuzzy=metadata_fuzzy,
                top_k=top_k,
                collection_filter=collection_filter,
                metadata_queries=metadata,
                metadata_fuzzy=metadata_fuzzy,
                metadata_threshold=metadata_threshold,
                config=config_copy
            )
        
        # Format results using the shared function
        formatted_results = format_search_results(results)
        
        # Create response in the same format as the query endpoint
        response = QueryResponse(
            query=content_query or "Metadata search",
            results=formatted_results
        )
        
        return response
    except Exception as e:
        logger.error(f"Error in metadata search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error performing metadata search: {str(e)}")


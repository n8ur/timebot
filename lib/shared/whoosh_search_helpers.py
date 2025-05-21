# /usr/local/lib/timebot/lib/shared/whoosh_search_helpers.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# whoosh_search_helpers.py

from typing import Dict, Any, List, Optional, Union, Tuple
import logging
from urllib.parse import urlparse

# Import the core search function from the sibling module
from .whoosh_search_core import metadata_search

# Add logger
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS ---

def search_sender(
    index_dir: str,
    sender: str,
    fuzzy: bool = False, # Fuzzy generally not useful/applicable with QueryParser approach here
    limit: int = 10,
    sort_by: str = "date",
    reverse: bool = True
) -> List[Dict[str, Any]]:
    """
    Search for emails from a specific sender.
    Handles obfuscation of email addresses if needed.

    Args:
        index_dir: Directory path for the Whoosh index
        sender: Sender email (e.g., user@example.com) or obfuscated form.
        fuzzy: (Currently ignored due to QueryParser use for sender field).
        limit: Maximum number of results to return
        sort_by: Field to sort results by (default: date)
        reverse: Whether to reverse the sort order (default: newest first)

    Returns:
        List of matching emails
    """
    sender_query_value = sender # Start with the original value

    # --- OBFUSCATION LOGIC ---
    # If input looks like a standard email, convert to obfuscated format
    if isinstance(sender, str) and '@' in sender:
        obfuscated_value = sender.replace('@', ' at ')
        logger.info(f"search_sender: Input '{sender}' looks like email, obfuscating to '{obfuscated_value}' for search.")
        sender_query_value = obfuscated_value
    else:
         logger.debug(f"search_sender: Input '{sender}' not obfuscated, using as is.")
    # --- END OBFUSCATION LOGIC ---

    # Call metadata_search with the potentially obfuscated value
    # Note: fuzzy=False passed to metadata_search for the metadata filter part
    return metadata_search(
        index_dir=index_dir,
        metadata_filters={"from_": sender_query_value},
        limit=limit,
        sort_by=sort_by,
        reverse=reverse,
        fuzzy=False, # Fuzzy not applied to metadata filters when using QueryParser
        collection_type="email"
    )


def search_date_range(
    index_dir: str,
    start_date: str, # Use None for open start
    end_date: str,   # Use None for open end
    limit: int = 10,
    sort_by: str = "date",
    reverse: bool = True,
    collection_type: str = None # e.g., "email", "document", "technical"
) -> List[Dict[str, Any]]:
    """
    Search for documents within a date range using TermRange.

    Args:
        index_dir: Directory path for the Whoosh index
        start_date: Start date (string, YYYY or YYYY-MM-DD...) or None.
        end_date: End date (string, YYYY or YYYY-MM-DD...) or None.
        limit: Maximum number of results to return
        sort_by: Field to sort results by
        reverse: Whether to reverse the sort order
        collection_type: Type of collection to determine date field.

    Returns:
        List of matching documents
    """
    # Determine the correct date field based on collection type
    # Default to 'date' if not specified or unknown type
    date_field = "date"
    if collection_type == "technical":
        # Example: technical documents might use 'publication_date'
        # Adjust this logic based on your actual schemas
        # Check schema dynamically? For now, hardcode based on known types.
        # ix = open_dir(index_dir) # Opening index just to check schema is inefficient here
        # if "publication_date" in ix.schema:
        #      date_field = "publication_date"
        # ix.close()
        # Hardcoding for now:
        date_field = "publication_date"
        logger.debug(f"Using date field '{date_field}' for collection type '{collection_type}'")
    elif collection_type == "web":
        # Skip date range search for web documents as captured_at isn't meaningful
        logger.warning(f"Date range search not recommended for web documents. Skipping search.")
        return [] # Return empty list for web date range search
    else:
         logger.debug(f"Using default date field 'date' for collection type '{collection_type}'")

    # Pass the tuple directly to metadata_search, which now handles TermRange
    return metadata_search(
        index_dir=index_dir,
        metadata_filters={date_field: (start_date, end_date)},
        limit=limit,
        sort_by=sort_by, # Use the specified sort_by field
        reverse=reverse,
        collection_type=collection_type # Pass original collection type
    )


def search_subject_or_title(
    index_dir: str,
    text: str,
    collection_type: str, # "email", "document", "technical", "web"
    fuzzy: bool = False, # Fuzzy not applied here due to QueryParser use
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search for documents by subject (emails) or title (documents/web).
    Uses QueryParser for the search text.

    Args:
        index_dir: Directory path for the Whoosh index
        text: Text to search for in subject/title
        collection_type: Type of collection ("email", "document", "technical", "web")
        fuzzy: (Currently ignored due to QueryParser use for these fields).
        limit: Maximum number of results to return

    Returns:
        List of matching documents
    """
    # Determine field based on collection type
    if collection_type == "email":
        field = "subject"
    elif collection_type in ["document", "technical", "web"]:
        field = "title"
    else:
        logger.error(f"Unknown collection_type '{collection_type}' in search_subject_or_title. Cannot determine field.")
        return []
    logger.debug(f"Searching field '{field}' for text '{text}' in collection type '{collection_type}'")

    return metadata_search(
        index_dir=index_dir,
        metadata_filters={field: text},
        limit=limit,
        fuzzy=False, # Fuzzy not applied to metadata filters when using QueryParser
        collection_type=collection_type
    )


def search_author(
    index_dir: str,
    author: str,
    fuzzy: bool = False, # Fuzzy not applied here due to QueryParser use
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search for documents by author (for document/technical collections).
    Uses QueryParser for the author name.

    Args:
        index_dir: Directory path for the Whoosh index
        author: Author name to search for
        fuzzy: (Currently ignored due to QueryParser use for author field).
        limit: Maximum number of results to return

    Returns:
        List of matching documents
    """
    # This function is intended for document/technical collections
    # Email sender search should use search_sender
    logger.debug(f"Searching 'author' field for '{author}' (intended for non-email collections)")
    return metadata_search(
        index_dir=index_dir,
        metadata_filters={"author": author},
        limit=limit,
        fuzzy=False, # Fuzzy not applied to metadata filters when using QueryParser
        collection_type="document" # Assume document/technical context
    )


def search_domain(
    index_dir: str,
    domain: str,
    fuzzy: bool = False,
    limit: int = 10,
    sort_by: str = "captured_at",
    reverse: bool = True
) -> List[Dict[str, Any]]:
    """
    Search for web documents from a specific domain.

    Args:
        index_dir: Directory path for the Whoosh index
        domain: Domain name to search for (e.g., "febo.com")
        fuzzy: (Currently ignored due to QueryParser use for domain field)
        limit: Maximum number of results to return
        sort_by: Field to sort results by (default: captured_at)
        reverse: Whether to reverse the sort order (default: newest first)

    Returns:
        List of matching web documents
    """
    logger.debug(f"Searching 'domain' field for '{domain}' in web collection")
    return metadata_search(
        index_dir=index_dir,
        metadata_filters={"domain": domain},
        limit=limit,
        sort_by=sort_by,
        reverse=reverse,
        fuzzy=False,
        collection_type="web"
    )


def search_source_url(
    index_dir: str,
    url_pattern: str,
    fuzzy: bool = False,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search for web documents by source URL pattern.
    Handles both exact matching and content-based URL search.

    Args:
        index_dir: Directory path for the Whoosh index
        url_pattern: URL pattern to search for
        fuzzy: Whether to use fuzzy matching for content search
        limit: Maximum number of results to return

    Returns:
        List of matching web documents
    """
    logger.debug(f"Searching for URL pattern '{url_pattern}' in web collection")

    # Try exact match first
    exact_results = metadata_search(
        index_dir=index_dir,
        metadata_filters={"source_url": url_pattern},
        limit=limit,
        fuzzy=False,
        collection_type="web"
    )

    if exact_results:
        logger.debug(f"Found {len(exact_results)} results with exact URL match")
        return exact_results

    # If no exact match, try content search for the URL
    logger.debug(f"No exact URL match found, trying content search for URL")

    # Extract domain and path for more targeted search
    try:
        # from urllib.parse import urlparse # Already imported at top
        parsed_url = urlparse(url_pattern)
        domain = parsed_url.netloc
        path = parsed_url.path.strip('/')

        # Search for domain in domain field
        domain_results = metadata_search(
            index_dir=index_dir,
            metadata_filters={"domain": domain},
            limit=limit,
            fuzzy=False,
            collection_type="web"
        )

        if domain_results:
            logger.debug(f"Found {len(domain_results)} results with domain match")

            # Filter results that contain the path in content or source_url
            if path:
                filtered_results = []
                for result in domain_results:
                    content = result.get("content", "").lower()
                    source_url = result.get("source_url", "").lower()
                    if path.lower() in content or path.lower() in source_url:
                        filtered_results.append(result)

                if filtered_results:
                    logger.debug(f"Filtered to {len(filtered_results)} results containing path '{path}'")
                    return filtered_results

            return domain_results

        # If no domain match, try content search for the full URL
        content_results = metadata_search(
            index_dir=index_dir,
            metadata_filters={},
            query_str=url_pattern,
            content_fields=["content"],
            limit=limit,
            fuzzy=fuzzy,
            collection_type="web"
        )

        if content_results:
            logger.debug(f"Found {len(content_results)} results with URL in content")
            return content_results

        # Last resort: try searching for just the path in content
        if path:
            path_results = metadata_search(
                index_dir=index_dir,
                metadata_filters={},
                query_str=path,
                content_fields=["content"],
                limit=limit,
                fuzzy=fuzzy,
                collection_type="web"
            )

            if path_results:
                logger.debug(f"Found {len(path_results)} results with path in content")
                return path_results

    except Exception as e:
        logger.error(f"Error in URL parsing or search: {e}", exc_info=True)

    logger.debug("No results found for URL pattern")
    return []


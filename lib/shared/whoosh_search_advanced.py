# /usr/local/lib/timebot/lib/shared/whoosh_search_advanced.py

from typing import Dict, Any, List, Optional, Union, Tuple
from whoosh.index import open_dir
from whoosh.spelling import Corrector
import logging
import os # Import os for path check in cross_collection_search

# Import the core search function from the sibling module
from .whoosh_search_core import metadata_search

# Add logger
logger = logging.getLogger(__name__)

# --- Suggest Corrections ---
def suggest_corrections(
    index_dir: str,
    misspelled_term: str,
    field: str,
    max_suggestions: int = 5
) -> List[str]:
    """
    Suggest spelling corrections for a term based on the index.

    Args:
        index_dir: Directory path for the Whoosh index
        misspelled_term: Potentially misspelled term
        field: Field to check for corrections
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of suggested corrections
    """
    logger.debug(f"Suggesting corrections for term '{misspelled_term}' in field '{field}'")
    ix = None
    searcher = None
    suggestions = []
    try:
        ix = open_dir(index_dir)
        searcher = ix.searcher()
        if field not in ix.schema:
             logger.error(f"Field '{field}' not found in schema for suggestions.")
             return []
        corrector = searcher.corrector(field)
        suggestions = corrector.suggest(misspelled_term, limit=max_suggestions)
        logger.debug(f"Found suggestions: {suggestions}")
    except Exception as e:
         logger.error(f"Error getting suggestions: {e}", exc_info=True)
    finally:
        if searcher:
            try: searcher.close()
            except: pass
        if ix:
             try: ix.close()
             except: pass

    return suggestions


# --- Cross Collection Search ---
def cross_collection_search(
    index_dirs: List[str],
    query_str: str = None,
    metadata_filters: Dict[str, Union[str, List[str], Tuple[str, str]]] = None,
    limit_per_collection: int = 5,
    total_limit: int = 10,
    collection_types: List[str] = None, # Should match index_dirs order
    fuzzy: bool = False # Fuzzy for query_str
) -> List[Dict[str, Any]]:
    """
    Search across multiple collections and combine results using revised metadata_search.

    Args:
        index_dirs: List of directory paths for Whoosh indexes
        query_str: Optional content query string (fuzzy applies here)
        metadata_filters: Dictionary of metadata filters to apply (generic names)
        limit_per_collection: Maximum results per collection before combining
        total_limit: Maximum total results to return after combining/sorting
        collection_types: List of collection types corresponding to index_dirs
        fuzzy: Whether fuzzy matching applies to query_str

    Returns:
        Combined list of matching documents from all collections, sorted by score.
    """
    logger.info(f"Starting cross-collection search across {len(index_dirs)} indexes.")
    if not metadata_filters:
        metadata_filters = {}
    if not collection_types:
        # Try to infer from path? Risky. Default to unknown.
        collection_types = ["unknown"] * len(index_dirs)
        logger.warning("Collection types not provided for cross-collection search.")
    elif len(collection_types) != len(index_dirs):
         logger.error("Mismatch between number of index_dirs and collection_types.")
         return [] # Or raise error

    all_results = []

    # Search each collection
    for i, index_dir in enumerate(index_dirs):
        collection_type = collection_types[i]
        logger.debug(f"Searching index {i+1}: '{index_dir}' (type: {collection_type})")

        # Adjust field names in filters based on collection type for this specific search
        adjusted_filters = {}
        for field, value in metadata_filters.items():
            target_field = field # Default to original field name
            # --- Apply Mappings ---
            if field == "author":
                if collection_type == "email":
                    target_field = "from_"
                    # Obfuscation logic is now handled within search_sender if called,
                    # or within rag.metadata_search if called from there.
                    # If cross_collection_search is called directly with author: email@addr,
                    # the obfuscation needs to happen HERE or be pushed down.
                    # Let's add it here for direct calls to cross_collection_search.
                    query_value = value
                    if isinstance(value, str) and '@' in value:
                         obfuscated_value = value.replace('@', ' at ')
                         logger.info(f"cross_collection_search: Obfuscating author '{value}' to '{obfuscated_value}' for email index.")
                         query_value = obfuscated_value
                    adjusted_filters[target_field] = query_value
                else: # document, technical, etc. use 'author'
                    adjusted_filters[target_field] = value

            elif field == "title":
                if collection_type == "email":
                    target_field = "subject"
                # else: keep 'title' for docs/technical/web
                adjusted_filters[target_field] = value

            elif field == "date":
                 # Handle potential different date fields if necessary
                 temp_ix = None
                 try:
                     if os.path.exists(index_dir) and os.listdir(index_dir):
                         temp_ix = open_dir(index_dir)
                         if collection_type == "technical" and "publication_date" in temp_ix.schema:
                             target_field = "publication_date"
                         elif collection_type == "web":
                             logger.debug(f"Ignoring date filter for web collection")
                             continue # Skip adding date filter for web
                         adjusted_filters[target_field] = value
                     else:
                         logger.warning(f"Index dir {index_dir} not found or empty during date field check.")
                         adjusted_filters[target_field] = value # Default to 'date' if check fails
                 except Exception as check_e:
                     logger.error(f"Error checking schema for date field in {index_dir}: {check_e}")
                     adjusted_filters[target_field] = value # Default to 'date' on error
                 finally:
                     if temp_ix: temp_ix.close()

            elif field == "url" and collection_type == "web":
                # For web documents, use source_url instead of url
                target_field = "source_url"
                adjusted_filters[target_field] = value
            else:
                # Use field name as is for others
                adjusted_filters[field] = value
        logger.debug(f"Adjusted filters for {collection_type}: {adjusted_filters}")

        # Search this collection using the revised metadata_search
        try:
            results = metadata_search(
                index_dir=index_dir,
                metadata_filters=adjusted_filters,
                query_str=query_str,
                limit=limit_per_collection,
                collection_type=collection_type,
                fuzzy=fuzzy # Pass fuzzy flag for query_str processing
            )
            logger.debug(f"Found {len(results)} results from index '{index_dir}'.")
            # Ensure results have a score field for sorting
            for res in results:
                if 'score' not in res: res['score'] = 0.0
            all_results.extend(results)
        except Exception as e:
             logger.error(f"Error searching index '{index_dir}': {e}", exc_info=True)
             # Continue with other indexes

    # Sort combined results by score (descending) and limit
    all_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    logger.info(f"Combined {len(all_results)} results from all indexes. Limiting to {total_limit}.")

    return all_results[:total_limit]


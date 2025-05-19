# /usr/local/lib/timebot/lib/rag/search_logic.py
"""
Core search logic for the RAG application. (Minimally modified for comma-separated filters)
"""

import sys
import uuid
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Import search functions
from shared.whoosh_utils import metadata_search as whoosh_metadata_search
from shared.chromadb_utils import (
        search_emails_unified as chroma_search_emails_unified,
        search_documents_unified as chroma_search_documents_unified,
        search_web_unified as chroma_search_web_unified,
        open_collection
        )

# Import optional modules with error handling
from rag.weighting import apply_weighting, apply_diversity_weights, \
        apply_final_weights; WEIGHTING_ENABLED = True
from rag.text_processing import deduplicate_by_content; DEDUPLICATION_ENABLED = True
from rag.reranking import rerank_results; RERANKING_ENABLED = True

# Import metadata search function
from rag.metadata_search import search_by_whoosh_metadata

_opened_collections = set()

def initialize_collections(config):
    """Initialize and open ChromaDB collections."""
    global _opened_collections
    if not config: logger.error("Config missing for initialize_collections."); return False
    try:
        db_path = config["CHROMADB_PATH"]
        embedding_model = config.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        collections_to_init = {
            "email": config.get("CHROMADB_EMAIL_COLLECTION"),
            "document": config.get("CHROMADB_DOC_COLLECTION"),
            "web": config.get("CHROMADB_WEB_COLLECTION")
        }
        opened_count = 0
        for col_type, collection_name in collections_to_init.items():
            if not collection_name: continue
            if collection_name not in _opened_collections:
                logger.info(f"Opening ChromaDB {col_type} collection: {collection_name}")
                open_collection(collection_name=collection_name, db_path=db_path, embedding_model_name=embedding_model)
                _opened_collections.add(collection_name)
                opened_count += 1
        logger.info(f"ChromaDB initialization complete. Opened {opened_count} new collections.")
        return True
    except KeyError as e: logger.error(f"Missing required ChromaDB config key: {e}"); return False
    except Exception as e: logger.error(f"Error initializing ChromaDB collections: {e}", exc_info=True); return False

def ensure_float_scores(results):
    """Ensure all scores in the results are floats."""
    processed = []
    for result in results:
        new_result = result.copy()
        score = new_result.get("score")
        if score is None: new_result["score"] = 0.0
        elif not isinstance(score, (float, int)):
            try: new_result["score"] = float(score)
            except (ValueError, TypeError): new_result["score"] = 0.0
        elif isinstance(score, int): new_result["score"] = float(score)
        processed.append(new_result)
    return processed

def search_whoosh_wrapper(query, fuzzy, collection_filter, top_k, config):
    """
    Wrapper function to search Whoosh using metadata_search for better results.
    Handles content queries across relevant fields based on collection type.
    """
    results = []
    if not config:
        logger.error("Whoosh wrapper missing config.")
        return []
    if not query or not query.strip():
        logger.info("Whoosh wrapper received empty query, skipping search.")
        return []

    logger.info(
        f"Initiating Whoosh search via metadata_search wrapper for query: '{query}'"
    )

    # --- Determine which collections to search ---
    search_emails_flag = False
    search_docs_flag = False
    search_web_flag = False
    if collection_filter == "all":
        search_emails_flag = search_docs_flag = search_web_flag = True
    elif isinstance(collection_filter, str):
        requested_collections = {
            cf.strip() for cf in collection_filter.split(",") if cf.strip()
        }
        if "emails" in requested_collections:
            search_emails_flag = True
        if "documents" in requested_collections:
            search_docs_flag = True
        if "web" in requested_collections:
            search_web_flag = True
    # --- End determination ---

    try:
        # Search Emails
        if search_emails_flag:
            email_index_dir = config.get("WHOOSHDB_EMAIL_PATH")
            if email_index_dir:
                logger.debug(f"Searching emails in {email_index_dir}")
                email_results = whoosh_metadata_search(
                    index_dir=email_index_dir,
                    metadata_filters={},  # No specific metadata filters here
                    query_str=query,
                    content_fields=[
                        "content",
                        "subject",
                        "from_",
                    ], # Search query in these fields
                    limit=top_k,
                    fuzzy=fuzzy, # Apply fuzzy to the query_str
                    collection_type="email",
                )
                logger.debug(f"Found {len(email_results)} raw email results.")
                results.extend(email_results) # metadata_search returns dicts
            else:
                logger.warning("WHOOSHDB_EMAIL_PATH not configured.")

        # Search Documents (covers 'document' and 'technical' schemas)
        if search_docs_flag:
            doc_index_dir = config.get("WHOOSHDB_DOC_PATH")
            if doc_index_dir:
                logger.debug(f"Searching documents in {doc_index_dir}")
                # Determine if it's the 'technical' schema to include more fields
                # This is a bit heuristic; ideally, config would specify schema type
                # For now, assume if WHOOSHDB_DOC_PATH is set, it might be technical
                # A safer approach might be needed if you have distinct simple/technical doc indexes
                doc_content_fields = ["content", "title", "author", "publisher"]
                # Add technical fields if they likely exist
                # if "technical" in doc_index_dir: # Example heuristic
                #    doc_content_fields.extend(["publisher_id", "source"])

                doc_results = whoosh_metadata_search(
                    index_dir=doc_index_dir,
                    metadata_filters={},
                    query_str=query,
                    content_fields=doc_content_fields,
                    limit=top_k,
                    fuzzy=fuzzy,
                    collection_type="document", # Or "technical" if distinguishable
                )
                logger.debug(f"Found {len(doc_results)} raw document results.")
                results.extend(doc_results)
            else:
                logger.warning("WHOOSHDB_DOC_PATH not configured.")

        # Search Web
        if search_web_flag:
            web_index_dir = config.get("WHOOSHDB_WEB_PATH")
            if web_index_dir:
                logger.debug(f"Searching web in {web_index_dir}")
                web_results = whoosh_metadata_search(
                    index_dir=web_index_dir,
                    metadata_filters={},
                    query_str=query,
                    content_fields=[
                        "content",
                        "title",
                        "domain",
                        "source_url",
                    ], # Search query in these fields
                    limit=top_k,
                    fuzzy=fuzzy,
                    collection_type="web",
                )
                logger.debug(f"Found {len(web_results)} raw web results.")
                results.extend(web_results)
            else:
                logger.warning("WHOOSHDB_WEB_PATH not configured.")

    except KeyError as e:
        logger.error(f"Missing config key in Whoosh wrapper: {e}")
    except Exception as e:
        logger.error(
            f"Error in Whoosh search wrapper using metadata_search: {e}",
            exc_info=True,
        )

    logger.info(f"Whoosh wrapper finished, returning {len(results)} total results.")
    # The results are already dictionaries, ready for downstream processing
    return results


def search_chroma_wrapper(query, similarity_threshold, collection_filter, top_k, config):
    """Wrapper function to search ChromaDB based on collection filter."""
    results = []
    if not config: logger.error("Chroma wrapper missing config."); return []

    try:
        if not initialize_collections(config): return [] # Cannot proceed

        # --- Determine which collections to search ---
        search_emails_flag = False
        search_docs_flag = False
        search_web_flag = False
        if collection_filter == "all":
            search_emails_flag = search_docs_flag = search_web_flag = True
        elif isinstance(collection_filter, str):
            requested_collections = {cf.strip() for cf in collection_filter.split(',') if cf.strip()}
            if "emails" in requested_collections: search_emails_flag = True
            if "documents" in requested_collections: search_docs_flag = True
            if "web" in requested_collections: search_web_flag = True
        # --- End determination ---

        # Search Emails
        if search_emails_flag: # Use flag
            email_collection = config.get("CHROMADB_EMAIL_COLLECTION")
            if email_collection:
                email_results = chroma_search_emails_unified(
                    collection_name=email_collection, query=query, limit=top_k, similarity_threshold=similarity_threshold
                )
                for result in email_results:
                    if hasattr(result, 'to_dict'): results.append(result.to_dict())
                    else: results.append(dict(result))
            else: logger.warning("CHROMADB_EMAIL_COLLECTION not configured.")

        # Search Documents
        if search_docs_flag: # Use flag
            doc_collection = config.get("CHROMADB_DOC_COLLECTION")
            if doc_collection:
                doc_results = chroma_search_documents_unified(
                    collection_name=doc_collection, query=query, limit=top_k, similarity_threshold=similarity_threshold
                )
                for result in doc_results:
                    if hasattr(result, 'to_dict'): results.append(result.to_dict())
                    else: results.append(dict(result))
            else: logger.warning("CHROMADB_DOC_COLLECTION not configured.")

        # Search Web
        if search_web_flag: # Use flag
            web_collection = config.get("CHROMADB_WEB_COLLECTION")
            if web_collection:
                web_results = chroma_search_web_unified(
                    collection_name=web_collection, query=query, limit=top_k, similarity_threshold=similarity_threshold
                )
                for result in web_results:
                    if hasattr(result, 'to_dict'): results.append(result.to_dict())
                    else: results.append(dict(result))
            else: logger.warning("CHROMADB_WEB_COLLECTION not configured.")

    except KeyError as e: logger.error(f"Missing config key in Chroma wrapper: {e}")
    except Exception as e: logger.error(f"Error in ChromaDB search wrapper: {e}", exc_info=True)
    return results

# --- perform_search_logic (Main Orchestration Function - Unchanged from Original) ---
def perform_search_logic(
    query,
    mode="combined",
    fuzzy=None,
    similarity_threshold=None,
    use_reranking=None,
    top_k=10,
    collection_filter="all",
    metadata_queries=None,
    metadata_fuzzy=True,
    metadata_threshold=0.8,
    config=None
):
    """
    Implements the common search logic used by both web UI and API endpoints.
    (Original logic calling the wrappers)
    """
    # Get default values from config if not provided
    if config:
        fuzzy = fuzzy if fuzzy is not None else config.get("DEFAULT_FUZZY_SEARCH", True)
        similarity_threshold = similarity_threshold if similarity_threshold is not None else config.get("DEFAULT_SIMILARITY_THRESHOLD", 0.5)
        use_reranking_cfg = config.get("USE_RERANKING", True) and RERANKING_ENABLED
        use_reranking = use_reranking if use_reranking is not None else use_reranking_cfg
        if use_reranking and not use_reranking_cfg: use_reranking = False # Respect config override
        use_weighting_cfg = config.get("USE_WEIGHTING", False) and WEIGHTING_ENABLED
        if mode == "chroma" or mode == "combined": initialize_collections(config)
    else:
        fuzzy = fuzzy if fuzzy is not None else True
        similarity_threshold = similarity_threshold if similarity_threshold is not None else 0.5
        use_reranking = use_reranking if use_reranking is not None else RERANKING_ENABLED
        use_weighting_cfg = WEIGHTING_ENABLED
        logger.warning("Config not provided to perform_search_logic, using defaults.")

    results = []
    reranking_applied = False
    is_metadata_search = bool(metadata_queries and any(metadata_queries.values()))
    is_content_search = bool(query and query.strip())

    # Metadata search path (unchanged)
    if is_metadata_search:
        logger.info(f"Performing metadata search with queries: {metadata_queries}")
        try:
            metadata_results = search_by_whoosh_metadata(
                metadata_queries=metadata_queries, content_query=query if is_content_search else None,
                fuzzy=metadata_fuzzy, top_k=top_k, collection_filter=collection_filter, config=config
            )
            if metadata_results:
                results = metadata_results
                logger.info(f"Metadata search returned {len(results)} results")
                if not is_content_search or mode != "combined":
                    return ensure_float_scores(results)[:top_k]
            else: logger.info("Metadata search returned no results, falling back.")
        except Exception as e: logger.error(f"Error in metadata search: {e}", exc_info=True)

    if not is_content_search and results: return ensure_float_scores(results)[:top_k]

    # Content search path (unchanged, calls modified wrappers)
    if is_content_search:
        regular_results = []
        if mode == "whoosh" or mode == "combined":
            try:
                whoosh_results = search_whoosh_wrapper(query=query, fuzzy=fuzzy, collection_filter=collection_filter, top_k=top_k, config=config)
                regular_results.extend(whoosh_results)
            except Exception as e: logger.error(f"Error in Whoosh search call: {e}", exc_info=True)
        if mode == "chroma" or mode == "combined":
            try:
                chroma_results = search_chroma_wrapper(query=query, similarity_threshold=similarity_threshold, collection_filter=collection_filter, top_k=top_k, config=config)
                regular_results.extend(chroma_results)
            except Exception as e: logger.error(f"Error in ChromaDB search call: {e}", exc_info=True)

        # Merge results (unchanged)
        if results:
            metadata_ids = {r.get("id") for r in results if r.get("id")}
            added_count = 0
            for result in regular_results:
                 if isinstance(result, dict):
                     res_id = result.get("id")
                     if res_id and res_id not in metadata_ids:
                         results.append(result); metadata_ids.add(res_id); added_count += 1
            logger.info(f"Merged {added_count} unique regular results with metadata results.")
        else: results = regular_results

    # Post-processing (unchanged)
    results = ensure_float_scores(results)
    if use_weighting_cfg:
        logger.info("Applying diversity weighting before reranking")
        results = apply_diversity_weights(results, config=config)
    if DEDUPLICATION_ENABLED:
        original_count = len(results)
        results = deduplicate_by_content(results)
        if len(results) < original_count: logger.info(f"Deduplicated {original_count - len(results)} results.")
    if use_reranking and is_content_search and len(results) > 1:
        logger.info(f"Attempting reranking for {len(results)} results.")
        try:
            reranker_model = config.get("RERANKER_MODEL") if config else None
            if reranker_model:
                 results = rerank_results(query, results, reranker_model)
                 logger.info("Reranking applied successfully."); reranking_applied = True
            else: logger.warning("Reranking enabled but RERANKER_MODEL not configured.")
        except Exception as e: logger.warning(f"Reranking failed: {e}", exc_info=True)
    if use_weighting_cfg:
        logger.info("Applying final weighting.")
        results = apply_final_weights(results, config)
    results.sort(key=lambda x: x.get("score", 0.0) if isinstance(x.get("score"), (int, float)) else 0.0, reverse=True)
    final_results = results[:top_k]
    logger.info(f"Returning final {len(final_results)} results.")

    # Final field check (unchanged)
    for result in final_results:
        if not isinstance(result, dict): continue
        if "metadata" not in result: result["metadata"] = {}
        if "content" not in result: result["content"] = result.get("text", "")
        if "id" not in result: result["id"] = result.get("docid", str(uuid.uuid4()))

    return final_results


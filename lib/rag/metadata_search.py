# /usr/local/lib/timebot/lib/rag/metadata_search.py

"""
Metadata search functionality for the RAG application.
"""

from typing import Dict, List, Any, Optional, Tuple, Union
import logging
import os
import uuid # Import uuid for fallback ID generation

logger = logging.getLogger(__name__)

# Inside /usr/local/lib/timebot/lib/rag/metadata_search.py
# Make sure logging is set up (it should be based on your other files)
import logging
logger = logging.getLogger(__name__)
# Import the shared search function correctly
from shared.whoosh_utils import metadata_search as shared_metadata_search # Use the utils path

# ... (keep existing imports)

def search_by_whoosh_metadata(
    metadata_queries: Dict[str, str],
    content_query: Optional[str] = None,
    fuzzy: bool = True, # Note: this fuzzy likely applies to content_query if present
    top_k: int = 100,
    collection_filter: str = "all",
    config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Performs a search directly using Whoosh's index for metadata fields.
    (Existing docstring...)
    """
    # --- DETAILED LOGGING ---
    logger.info("--- Entering search_by_whoosh_metadata ---")
    logger.info(f"Received metadata_queries: {metadata_queries}")
    logger.info(f"Received content_query: {content_query}")
    logger.info(f"Received fuzzy: {fuzzy}, top_k: {top_k}, collection_filter: {collection_filter}")
    # --- END LOGGING ---

    if not config:
        logger.error("No configuration provided for Whoosh metadata search")
        return []

    # Get index paths from config
    email_index_dir = config.get("WHOOSHDB_EMAIL_PATH")
    document_index_dir = config.get("WHOOSHDB_DOC_PATH")
    web_index_dir = config.get("WHOOSHDB_WEB_PATH")

    # Check index paths availability based on filter
    can_search_emails = collection_filter in ["all", "emails"] and email_index_dir
    can_search_docs = collection_filter in ["all", "documents"] and document_index_dir
    can_search_web = collection_filter in ["all", "web"] and web_index_dir

    # ... (logging for missing paths remains useful) ...

    all_formatted_results = []

    # --- Process input metadata_queries into generic filters ---
    generic_metadata_filters = {}
    date_range_query = None
    for field, value in metadata_queries.items():
        if not value: logger.debug(f"Skipping empty query for field: {field}"); continue
        value_str = str(value) if value is not None else ""
        if field == "date" and " to " in value_str:
            try:
                start_date, end_date = value_str.split(" to ")
                date_range_query = (start_date.strip(), end_date.strip())
                logger.debug(f"Parsed date range query: {date_range_query}")
            except ValueError:
                logger.warning(f"Could not parse date range '{value_str}', treating as string filter.")
                generic_metadata_filters["date"] = value_str
        else:
            generic_metadata_filters[field] = value_str
    logger.debug(f"Processed generic metadata filters: {generic_metadata_filters}")
    if date_range_query: logger.debug(f"Date range query detected: {date_range_query}")
    # --- END PROCESSING ---


    # --- Perform EMAIL search ---
    if can_search_emails:
        logger.info("--- Preparing Email Search ---")
        email_metadata_filters = {}
        # Map generic names to email-specific names
        for field, value in generic_metadata_filters.items():
            if field == "title": email_metadata_filters["subject"] = value
            elif field == "author":
                # Apply obfuscation here
                obfuscated_value = value
                if isinstance(value, str) and '@' in value:
                    obfuscated_value = value.replace('@', ' at ')
                    logger.debug(f"Mapping/Obfuscating 'author' ({value}) to 'from_' ({obfuscated_value}) for email search.")
                else:
                    logger.debug(f"Mapping 'author' to 'from_' for email search (value used as is: {value})")
                email_metadata_filters["from_"] = obfuscated_value # Use the potentially obfuscated value
            elif field != "date": # Handle date separately below
                 email_metadata_filters[field] = value

        # Apply date range or specific date string
        if date_range_query and "date" not in email_metadata_filters:
            email_metadata_filters["date"] = date_range_query
            logger.debug(f"Applying date range {date_range_query} to email search.")
        elif "date" in generic_metadata_filters: # Check generic filters for specific date string
             email_metadata_filters["date"] = generic_metadata_filters["date"]
             logger.debug(f"Using specific date string filter for emails: {email_metadata_filters['date']}")

        # --- DETAILED LOGGING ---
        logger.info(f"Attempting SHARED email search with filters: {email_metadata_filters}")
        logger.info(f"Email search content query: {content_query}")
        # --- END LOGGING ---
        try:
            # Call the SHARED function
            email_results = shared_metadata_search(
                index_dir=email_index_dir,
                metadata_filters=email_metadata_filters, # Pass the mapped/obfuscated filters
                query_str=content_query,
                content_fields=["content"] if content_query else None,
                limit=top_k * 5, # Fetch more initially if collapsing later
                fuzzy=fuzzy, # This fuzzy applies to content_query
                collection_type="email"
            )
            # --- DETAILED LOGGING ---
            logger.info(f"SHARED email search returned {len(email_results)} results.")
            # --- END LOGGING ---

            # Format results (using the function in this file)
            count = 0
            for result in email_results:
                try:
                    formatted_result = format_whoosh_result(result, "email")
                    all_formatted_results.append(formatted_result)
                    count += 1
                except Exception as format_e:
                     logger.error(f"Error formatting email result: {result}. Error: {format_e}", exc_info=True)
            logger.debug(f"Successfully formatted {count} email results.")

        except Exception as e:
            logger.error(f"--- ERROR DURING EMAIL SEARCH ---", exc_info=True)
            logger.error(f"Filters used during failed email search: {email_metadata_filters}")
    else:
         logger.info("Skipping email search (not requested or index path missing).")


    # --- Perform DOCUMENT search ---
    if can_search_docs:
        logger.info("--- Preparing Document Search ---")
        doc_metadata_filters = {}
        # Map generic names (mostly the same for docs)
        for field, value in generic_metadata_filters.items():
             if field != "date": # Handle date separately
                 doc_metadata_filters[field] = value

        # Apply date range or specific date string
        if date_range_query and "date" not in doc_metadata_filters:
            doc_metadata_filters["date"] = date_range_query # Use 'date' field for simple docs
            # If using 'technical' schema, might need 'publication_date'
            # doc_metadata_filters["publication_date"] = date_range_query
            logger.debug(f"Applying date range {date_range_query} to document search.")
        elif "date" in generic_metadata_filters:
             doc_metadata_filters["date"] = generic_metadata_filters["date"]
             # doc_metadata_filters["publication_date"] = generic_metadata_filters["date"]
             logger.debug(f"Using specific date string filter for documents: {doc_metadata_filters['date']}")

        # --- DETAILED LOGGING ---
        logger.info(f"Attempting SHARED document search with filters: {doc_metadata_filters}")
        logger.info(f"Document search content query: {content_query}")
        # --- END LOGGING ---
        try:
            # Call the SHARED function
            doc_results = shared_metadata_search(
                index_dir=document_index_dir,
                metadata_filters=doc_metadata_filters,
                query_str=content_query,
                content_fields=["content"] if content_query else None,
                limit=top_k * 5,
                fuzzy=fuzzy,
                collection_type="document" # Or "technical"
            )
            # --- DETAILED LOGGING ---
            logger.info(f"SHARED document search returned {len(doc_results)} results.")
            # --- END LOGGING ---

            # Format results
            count = 0
            for result in doc_results:
                try:
                    collection_type_fmt = "document"
                    if "parent_hash" in result or "chunk_number" in result:
                         collection_type_fmt = "technical"
                    formatted_result = format_whoosh_result(result, collection_type_fmt)
                    all_formatted_results.append(formatted_result)
                    count += 1
                except Exception as format_e:
                     logger.error(f"Error formatting document result: {result}. Error: {format_e}", exc_info=True)
            logger.debug(f"Successfully formatted {count} document/technical results.")

        except Exception as e:
             logger.error(f"--- ERROR DURING DOCUMENT SEARCH ---", exc_info=True)
             logger.error(f"Filters used during failed document search: {doc_metadata_filters}")
    else:
        logger.info("Skipping document search (not requested or index path missing).")

    # --- Perform WEB search ---
    if can_search_web:
        logger.info("--- Preparing Web Search ---")
        web_metadata_filters = {}
        url_search = False
        url_value = None
        for field, value in generic_metadata_filters.items():
            if field == "url" or field == "source_url": url_search = True; url_value = value
            elif field == "domain": web_metadata_filters["domain"] = value
            elif field == "title": web_metadata_filters["title"] = value
            elif field != "date": web_metadata_filters[field] = value # Ignore date for web

        # --- DETAILED LOGGING ---
        logger.info(f"Attempting SHARED web search with filters: {web_metadata_filters}")
        logger.info(f"Web search content query: {content_query}")
        logger.info(f"URL search flag: {url_search}, URL value: {url_value}")
        # --- END LOGGING ---
        try:
            web_results = []
            if url_search and url_value:
                # Assuming search_source_url is also in shared.whoosh_utils now
                from shared.whoosh_utils import search_source_url
                web_results = search_source_url(
                        index_dir=web_index_dir,
                        url_pattern=url_value,
                        fuzzy=fuzzy, # Does search_source_url use fuzzy? Check its signature
                        limit=top_k * 5
                )
                logger.info(f"SHARED URL search returned {len(web_results)} results")
            else:
                # Call the SHARED function
                web_results = shared_metadata_search(
                    index_dir=web_index_dir,
                    metadata_filters=web_metadata_filters,
                    query_str=content_query,
                    content_fields=["content"] if content_query else None,
                    limit=top_k * 5,
                    fuzzy=fuzzy,
                    collection_type="web"
                )
                # --- DETAILED LOGGING ---
                logger.info(f"SHARED regular web search returned {len(web_results)} results")
                # --- END LOGGING ---

            # Format results
            count = 0
            for result in web_results:
                try:
                    formatted_result = format_whoosh_result(result, "web")
                    all_formatted_results.append(formatted_result)
                    count += 1
                except Exception as format_e:
                    logger.error(f"Error formatting web result: {result}. Error: {format_e}", exc_info=True)
            logger.debug(f"Successfully formatted {count} web results.")

        except Exception as e:
            logger.error(f"--- ERROR DURING WEB SEARCH ---", exc_info=True)
            logger.error(f"Filters used during failed web search: {web_metadata_filters}")
    else:
        logger.info("Skipping web search (not requested or index path missing).")


    # --- Collapse results if metadata-only search ---
    # ... (rest of the function: collapsing, sorting, final logging) ...
    final_results = []
    if not content_query and any(r.get("parent_hash") for r in all_formatted_results): # Only collapse if needed
        logger.info("Metadata-only search detected AND chunked results present. Collapsing results by parent_hash.")
        unique_docs = {} # Store the best result per parent_hash or id
        for result in all_formatted_results:
            doc_key = result.get("parent_hash") or result.get("id")
            if not doc_key:
                 logger.warning(f"Result missing parent_hash and id, cannot collapse: {result.get('title', result.get('subject', 'N/A'))}")
                 continue
            current_score = result.get("score", 0.0)
            if doc_key not in unique_docs or current_score > unique_docs[doc_key].get("score", 0.0):
                unique_docs[doc_key] = result
        final_results = list(unique_docs.values())
        logger.info(f"Collapsed {len(all_formatted_results)} results into {len(final_results)} unique documents.")
    else:
        if not content_query:
             logger.info("Metadata-only search, but no chunked results found (parent_hash missing). Skipping collapse.")
        else:
             logger.info("Content query present. Returning all relevant chunks/items.")
        final_results = all_formatted_results

    # Sort final results by score (descending)
    final_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    # Limit to top_k results
    final_results = final_results[:top_k]

    logger.info(f"--- search_by_whoosh_metadata Complete ---")
    logger.info(f"Returning {len(final_results)} final results.")

    return final_results


# --- format_whoosh_result function (ensure it exists in this file) ---
# Needs to be present or imported correctly if moved elsewhere
# ... (implementation of format_whoosh_result) ...
import uuid # Make sure uuid is imported if needed by format_whoosh_result

def format_whoosh_result(result: Dict[str, Any], collection_type: str) -> Dict[str, Any]:
    """
    Format a Whoosh search result into a standardized FLAT dictionary.
    (Ensure this function is present and correct in this file)
    """
    formatted_result = {}
    raw_id = result.get("doc_id", result.get("id"))
    formatted_result["id"] = str(raw_id) if raw_id else str(uuid.uuid4())
    try:
        formatted_result["score"] = float(result.get("score", 0.0))
    except (ValueError, TypeError):
        formatted_result["score"] = 0.0
    formatted_result["content"] = result.get("content", "") # Add content here
    formatted_result["search_provider"] = f"Whoosh-{collection_type.capitalize()}"
    formatted_result["doc_type"] = collection_type
    formatted_result["url"] = result.get("url", "")

    if collection_type == "email":
        formatted_result["from"] = result.get("from_", "")
        formatted_result["date"] = result.get("date", "")
        formatted_result["subject"] = result.get("title", result.get("subject", "")) # Prefer title if present? Check schema
        formatted_result["source"] = "email"
        formatted_result["to"] = result.get("to", "")
        formatted_result["cc"] = result.get("cc", "")
    elif collection_type in ["document", "technical"]:
        formatted_result["title"] = result.get("title", "")
        formatted_result["author"] = result.get("author", "")
        formatted_result["date"] = result.get("publication_date", result.get("date", ""))
        formatted_result["publisher"] = result.get("publisher", "")
        formatted_result["source"] = result.get("source", collection_type)
        technical_fields = [
            "publisher_id", "sequence_number", "processing_date",
            "is_chunk", "chunk_number", "total_chunks",
            "parent_hash", "chunk_id"
        ]
        for field in technical_fields:
            if field in result and result[field] is not None:
                formatted_result[field] = result[field]
    elif collection_type == "web":
        formatted_result["title"] = result.get("title", "")
        formatted_result["source_url"] = result.get("source_url", "")
        formatted_result["captured_at"] = result.get("captured_at", "")
        formatted_result["domain"] = result.get("domain", "")
        formatted_result["url"] = result.get("source_url", "")
        formatted_result["source"] = "web"
        formatted_result["date"] = result.get("captured_at", "") # Use captured_at for date consistency

    standard_keys = set(formatted_result.keys()) | {"score", "doc_id", "id", "content", "from_", "publication_date"}
    for key, value in result.items():
        if key not in standard_keys and value is not None:
            formatted_result[key] = value

    required_keys = ["title", "author", "date", "subject", "from", "publisher", "url", "source", "doc_type", "content"]
    for key in required_keys:
        if key not in formatted_result:
             formatted_result[key] = ""

    return formatted_result



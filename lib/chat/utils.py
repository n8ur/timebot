# utils.py - Utility functions for the Timebot chat application

import datetime
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def format_context(rag_results: List[Dict[str, Any]]) -> str:
    """
    Format RAG results into a context string for the prompt, including web results.
    """
    if not rag_results:
        return "No relevant context found."

    context_parts = []
    for i, doc in enumerate(rag_results, 1):
        if not isinstance(doc, dict):
            logger.warning(f"Skipping invalid RAG result item: {doc}")
            continue

        # Extract content and metadata safely
        content = doc.get("content", "")
        metadata = doc.get("metadata", {})
        if not isinstance(metadata, dict):
            logger.warning(f"Result {i} has invalid metadata: {metadata}")
            metadata = {} # Use empty dict as fallback

        doc_type = metadata.get("doc_type", "unknown")
        doc_text = ""

        # Format based on document type
        if doc_type == "email":
            subject = metadata.get("subject", "No subject")
            from_field = metadata.get("from", "Unknown sender")
            date = metadata.get("date", "Unknown date")
            doc_text = (
                f"DOCUMENT {i} (Email):\n"
                f"Subject: {subject}\n"
                f"From: {from_field}\nDate: {date}\n\n{content}\n"
            )
        elif doc_type == "document":
            title = metadata.get("title", "Untitled document")
            author = metadata.get("author", "")
            publisher = metadata.get("publisher", "")
            pub_date = metadata.get("date", "Unknown date") # Use 'date' field

            # Build attribution string
            attribution_parts = []
            if author and author != "Unknown Author":
                attribution_parts.append(f"Author: {author}")
            if publisher and publisher != "Unknown Publisher":
                attribution_parts.append(f"Publisher: {publisher}")
            attribution = "\n".join(attribution_parts) if attribution_parts else "Source: Unknown"

            doc_text = (
                f"DOCUMENT {i} (Document):\n"
                f"Title: {title}\n"
                f"{attribution}\n"
                f"Date: {pub_date}\n\n{content}\n"
            )
        elif doc_type == "web": # *** ADDED HANDLING FOR WEB ***
            title = metadata.get("title", "Untitled Web Page")
            # Prioritize source_url, fallback to url
            url = metadata.get("source_url") or metadata.get("url", "Unknown URL")
            domain = metadata.get("domain", "Unknown domain")
            captured_at = metadata.get("captured_at", "Unknown scan date")

            doc_text = (
                f"DOCUMENT {i} (Web Page):\n"
                f"Title: {title}\n"
                f"Source URL: {url}\n"
                f"Domain: {domain}\n"
                f"Scanned: {captured_at}\n\n{content}\n"
            )
        else:
            # Generic format for unknown sources
            # Try to get a title or subject
            title = metadata.get("title") or metadata.get("subject", f"Unknown Document {i}")
            # Include other potentially useful metadata
            meta_items = [f"{k}: {v}" for k, v in metadata.items() if k not in ['doc_type', 'content', 'title', 'subject'] and v]
            metadata_str = "\n".join(meta_items)

            doc_text = (
                f"DOCUMENT {i} (Unknown Type):\n"
                f"Title: {title}\n"
                f"{metadata_str}\n\n{content}\n"
            )

        if doc_text: # Only append if we successfully formatted something
             context_parts.append(doc_text)

    # Join parts with a clear separator
    return "\n" + "\n---\n".join(context_parts) + "\n"


def format_references(rag_results: List[Dict[str, Any]]) -> str:
    """
    Format RAG results into a compact reference list with type-specific formatting.
    Handles email, document, and web types.
    """
    if not rag_results:
        return ""

    references = []
    for i, doc in enumerate(rag_results, 1):
        if not isinstance(doc, dict):
            logger.warning(f"Skipping invalid RAG result item for references: {doc}")
            continue

        reference = f"[{i}] Unknown Reference" # Default
        url = "#" # Default URL

        try:
            # Extract metadata safely
            metadata = doc.get("metadata", {})
            if not isinstance(metadata, dict):
                logger.warning(f"Result {i} has invalid metadata for references: {metadata}")
                metadata = {} # Use empty dict as fallback

            doc_type = metadata.get("doc_type", "unknown")
            url = metadata.get("url", "#") # Get base URL first

            # Format based on document type
            if doc_type == "email":
                subject = metadata.get("subject", "No subject")
                sender = metadata.get("from", "Unknown sender")
                date_str = metadata.get("date", "")
                date_display = date_str # Default display

                # Attempt to simplify date display
                if isinstance(date_str, str) and date_str:
                    try:
                        # Handle ISO format like 2020-01-17T21:09:08
                        if "T" in date_str:
                            date_display = date_str.split("T")[0]
                        # Handle format like Sun Jun 30 15:47:03 UTC 2013
                        elif "UTC" in date_str:
                             # Be careful with strptime, might fail on variations
                             date_obj = datetime.datetime.strptime(date_str, "%a %b %d %H:%M:%S %Z %Y")
                             date_display = date_obj.strftime("%Y-%m-%d")
                        # Fallback: try to extract year if possible
                        else:
                             parts = date_str.split()
                             if len(parts) > 0 and parts[-1].isdigit() and len(parts[-1]) == 4:
                                 date_display = parts[-1]
                    except Exception as e:
                        logger.debug(f"Could not parse date string '{date_str}': {e}")
                        # Keep original date_str if parsing fails

                reference = f'[{i}] Email: "{subject}"; {date_display}; {sender}'

            elif doc_type == "document":
                title = metadata.get("title", "Untitled document")
                publisher = metadata.get("publisher", "")
                author = metadata.get("author", "")

                # extract only the year
                raw_date_value = metadata.get("date", "")
                display_year = ""
                if isinstance(raw_date_value, str):
                    if len(raw_date_value) >= 4 and raw_date_value[:4].isdigit():
                        display_year = raw_date_value[:4] # Take first 4 digits if they are numeric
                    elif raw_date_value.isdigit() and len(raw_date_value) == 4:
                         display_year = raw_date_value # Handle case where it's just 'YYYY' as a string
                elif isinstance(raw_date_value, int):
                    if 1000 <= raw_date_value <= 9999: # Basic check for 4-digit year as int
                        display_year = str(raw_date_value)
                if display_year == "":
                    display_year = "Unknown"

                # Build attribution string
                attribution_parts = []
                if author and author != "Unknown Author": attribution_parts.append(author)
                if publisher and publisher != "Unknown Publisher": attribution_parts.append(publisher)
                if display_year: attribution_parts.append(display_year)
                attribution = "; ".join(attribution_parts) if attribution_parts else "Unknown source"

                # Build position string (only if multiple chunks)
                chunk_num = metadata.get("chunk_number")
                total_chunks = metadata.get("total_chunks")
                position_string = ""
                if isinstance(chunk_num, (int, float)) and isinstance(total_chunks, (int, float)) and total_chunks > 1:
                    try:
                        position_pct = round(((chunk_num - 1) / total_chunks) * 10) * 10
                        position_text = f"{position_pct}%"
                        if position_pct == 0: position_text = "Beginning"
                        elif position_pct >= 90: position_text = "End"
                        position_string = f"; Location: ~{position_text}" # Add comma separator
                    except Exception: pass # Ignore errors calculating position

                reference = f'[{i}] Document: "{title}"; {attribution}{position_string}'

            elif doc_type == "web":
                title = metadata.get("title", "Untitled Web Page")
                domain = metadata.get("domain", "")
                captured_at = metadata.get("captured_at", "")
                # Prioritize source_url for the link, fallback to url
                web_url = metadata.get("source_url") or url
                url = web_url if web_url and web_url != "#" else url # Update main url if source_url is better

                # Build position string (only if multiple chunks)
                chunk_num = metadata.get("chunk_number")
                total_chunks = metadata.get("total_chunks")
                position_string = ""
                if isinstance(chunk_num, (int, float)) and isinstance(total_chunks, (int, float)) and total_chunks > 1:
                    try:
                        position_pct = round(((chunk_num - 1) / total_chunks) * 10) * 10
                        position_text = f"{position_pct}%"
                        if position_pct == 0: position_text = "Beginning"
                        elif position_pct >= 90: position_text = "End"
                        position_string = f"; Location: ~{position_text}" # Add comma separator
                    except Exception: pass # Ignore errors calculating position

                ref_parts = [f'[{i}] Web Page: "{title}"']
                if domain: ref_parts.append(domain)
                if captured_at: ref_parts.append(f"Scanned: {captured_at}")
                if position_string: ref_parts.append(position_string)
                reference = "; ".join(ref_parts)

            else:
                # Fallback for unknown type
                title = metadata.get("title") or metadata.get("subject", f"Reference {i}")
                reference = f'[{i}] Reference: "{title}"'

            # Add URL link at the end if available and valid
            if url and url != "#" and url != "Unknown":
                # Basic check for common protocols
                if url.startswith("http://") or url.startswith("https://"):
                     reference += f" [Link]({url})"
                else:
                     logger.warning(f"Skipping invalid URL format for reference {i}: {url}")

        except Exception as e:
            logger.error(f"Error formatting reference for doc {i}: {e}", exc_info=True)
            # Use the default reference string in case of error
            reference = f"[{i}] Error Formatting Reference"
            # Still try to get a URL if possible
            try:
                fallback_url = doc.get("metadata", {}).get("url", "#")
                if fallback_url and fallback_url != "#" and fallback_url != "Unknown" and (fallback_url.startswith("http://") or fallback_url.startswith("https://")):
                    reference += f" [Link]({fallback_url})"
            except Exception:
                pass # Ignore errors during fallback URL retrieval

        references.append(reference)

    # Join with double newlines for clear separation in chat UI
    return "\n\n".join(references)



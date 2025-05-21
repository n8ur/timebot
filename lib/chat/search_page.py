# /usr/local/lib/timebot/lib/chat/search_page.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# search_page.py (Modified from Original)
import streamlit as st
from typing import List, Dict, Any, Optional
import math
import logging
import json
import requests # Keep requests import if perform_search might use it directly (though unlikely now)
from chat.ui import set_font_size, create_sidebar, render_footer

logger = logging.getLogger(__name__)

# --- Constants ---
MIN_SCORE_THRESHOLD = 0.025 # Minimum score to display relevance

# --- Helper Functions ---
def get_collection_filter(selections: Dict[str, bool]) -> str:
    """Constructs the collection filter string from checkbox selections."""
    selected = [key for key, value in selections.items() if value]
    if len(selected) == 3 or not selected: # All selected or none selected defaults to all
        return "all"
    # Return comma-separated string, e.g., "emails,web"
    return ",".join(sorted(selected))

def set_prepared_question(document_title):
    """Sets a prepared question in session state and navigates to chat."""
    st.session_state.prepared_question = f"Tell me more about '{document_title}'"
    # Clear page param to go back to main chat
    if "page" in st.query_params:
        st.query_params.clear()
    st.rerun()

def increment_page():
    """Increments the search results page number."""
    st.session_state.search_page += 1
    # Rerun needed to reflect page change if buttons are outside form
    st.rerun()

def decrement_page():
    """Decrements the search results page number."""
    st.session_state.search_page -= 1
    # Rerun needed to reflect page change
    st.rerun()

# --- Main Display Function ---
def display_search_page(query_rag_fn, query_metadata_fn=None):
    """Display the search interface and handle search queries"""
    set_font_size()
    create_sidebar(current_page="search")
    st.title("Search Knowledge Base")

    # --- Description Text (Updated) ---
    st.markdown(
        """
        You can enter a natural-language search query that will perform
        a similarity search of the database, or search document metadata
        by title/subject, publisher/source, author/from, and/or date fields.
        Combined content and metadata searches are possible.

        The content search is mainly a 'similarity' search and works best with
        'natural language' queries. It finds relevant matches but may not return *every*
        match.

        The metadata search uses exact text and supports boolean searches
        ('AND', 'OR', 'NOT', etc.) and grouping with parentheses. The "fuzzy"
        search option allows approximate matches for metadata terms.

        You can search the **Email**, **Document**, and/or **Web** collections.
        For email senders, use "user@domain.com" format. For document authors,
        note that only the first author may be listed. **The Author/From and Date
        fields do not apply to the Web collection.**

        In the results display, clicking the "Link" will take you to the full
        document or original web source.
        """
    )
    st.markdown("<hr style='margin: 10px 0; border: 0; border-top: 1px solid #eee;'>", unsafe_allow_html=True)

    # --- Initialize Session State ---
    # Basic search state
    if "search_results" not in st.session_state: st.session_state.search_results = []
    if "search_page" not in st.session_state: st.session_state.search_page = 1
    if "total_results" not in st.session_state: st.session_state.total_results = 0
    if "search_query" not in st.session_state: st.session_state.search_query = ""
    # Metadata state
    if "metadata_search" not in st.session_state:
        st.session_state.metadata_search = {"title": "", "author": "", "publisher": "", "date": ""}
    if "metadata_fuzzy" not in st.session_state: st.session_state.metadata_fuzzy = True
    # Form/UI state
    if "form_submitted" not in st.session_state: st.session_state.form_submitted = False
    if "metadata_form_key" not in st.session_state: st.session_state.metadata_form_key = 0 # Key to reset form inputs
    if "clear_search_clicked" not in st.session_state: st.session_state.clear_search_clicked = False
    if "search_mode" not in st.session_state: st.session_state.search_mode = "Smart (Auto-detect)"
    # Collection selection state
    if "collection_selection" not in st.session_state:
        st.session_state.collection_selection = {"emails": True, "documents": True, "web": True}
    # Form data capture (NEW)
    if "form_data" not in st.session_state:
        st.session_state.form_data = {
            "query": "",
            "title": "",
            "author": "",
            "publisher": "",
            "date": "",
            "fuzzy": True
        }

    # --- Handle Clear Button Click ---
    if st.session_state.clear_search_clicked:
        st.session_state.search_query = ""
        st.session_state.metadata_search = {"title": "", "author": "", "publisher": "", "date": ""}
        st.session_state.search_results = []
        st.session_state.total_results = 0
        st.session_state.search_page = 1
        st.session_state.collection_selection = {"emails": True, "documents": True, "web": True} # Reset checkboxes
        st.session_state.form_data = {"query": "", "title": "", "author": "", "publisher": "", "date": "", "fuzzy": True}
        st.session_state.metadata_form_key += 1 # Increment key to force form re-render
        st.session_state.clear_search_clicked = False # Reset flag
        st.rerun() # Force rerun after clearing

    # --- Callback Functions ---
    def handle_form_submission(): 
        st.session_state.form_submitted = True
        # Log current state for debugging
        logger.info(f"Form submitted. Current form data: {st.session_state.form_data}")
        
    def set_clear_search_flag(): st.session_state.clear_search_clicked = True

    # --- Search Mode Selection ---
    search_mode = st.radio(
        "Search Type",
        ["Smart (Auto-detect)", "Content Search", "Metadata Search", "Combined Search"],
        horizontal=True, help="Select how you want to search",
        index=["Smart (Auto-detect)", "Content Search", "Metadata Search", "Combined Search"].index(st.session_state.search_mode),
        key=f"search_mode_radio_{st.session_state.metadata_form_key}" # Link key to reset
    )
    st.session_state.search_mode = search_mode
    mode_mapping = {"Smart (Auto-detect)": "auto", "Content Search": "content_only", "Metadata Search": "metadata_only", "Combined Search": "combined"}
    internal_mode = mode_mapping[search_mode]

    # --- Collection Selection Checkboxes (OUTSIDE FORM) ---
    st.markdown("**Collections to search:**")
    cols_cb = st.columns(3)
    with cols_cb[0]:
        st.session_state.collection_selection["emails"] = st.checkbox("Emails", value=st.session_state.collection_selection["emails"], key=f"cb_emails_{st.session_state.metadata_form_key}")
    with cols_cb[1]:
        st.session_state.collection_selection["documents"] = st.checkbox("Documents", value=st.session_state.collection_selection["documents"], key=f"cb_docs_{st.session_state.metadata_form_key}")
    with cols_cb[2]:
        st.session_state.collection_selection["web"] = st.checkbox("Web", value=st.session_state.collection_selection["web"], key=f"cb_web_{st.session_state.metadata_form_key}")

    # Determine collection selection state for dynamic UI
    only_web_selected = (st.session_state.collection_selection["web"] and
                         not st.session_state.collection_selection["emails"] and
                         not st.session_state.collection_selection["documents"])
    web_selected_with_others = (st.session_state.collection_selection["web"] and
                                (st.session_state.collection_selection["emails"] or
                                 st.session_state.collection_selection["documents"]))

    # --- Search Form ---
    with st.form(key=f"search_form_{st.session_state.metadata_form_key}", clear_on_submit=False):
        # Content Search Input
        if internal_mode != "metadata_only":
            search_query = st.text_input(
                "Enter your search query", 
                value=st.session_state.search_query,
                key=f"query_input_{st.session_state.metadata_form_key}"
            )
        else:
            search_query = ""
            st.info("Using metadata filters only. Add at least one filter below.")

        # --- Metadata Search Section (with Dynamic Fields) ---
        # Always use values from session state to ensure persistence
        metadata_expanded = (internal_mode == "metadata_only" or 
                            internal_mode == "combined" or 
                            any(v for v in st.session_state.metadata_search.values() if v))
        
        with st.expander("Metadata Filters", expanded=metadata_expanded):
            metadata_col1, metadata_col2 = st.columns(2)
            with metadata_col1:
                title_search = st.text_input(
                    "Title/Subject", 
                    value=st.session_state.metadata_search.get("title", ""),
                    key=f"title_input_{st.session_state.metadata_form_key}"
                )
                
                # Author/From field with dynamic disabling/help text
                author_help = "Search by author or sender."
                if only_web_selected: author_help += " (Not applicable if only Web is selected)"
                elif web_selected_with_others: author_help += " (Note: Does not apply to Web results)"
                
                author_search = st.text_input(
                    "Author/From", 
                    value=st.session_state.metadata_search.get("author", ""),
                    help=author_help, 
                    key=f"author_input_{st.session_state.metadata_form_key}",
                    disabled=only_web_selected
                )
                
            with metadata_col2:
                publisher_search = st.text_input(
                    "Publisher/Source", 
                    value=st.session_state.metadata_search.get("publisher", ""),
                    help="Search by publisher or source (e.g., NIST, domain)",
                    key=f"publisher_input_{st.session_state.metadata_form_key}"
                )
                
                # Date field with dynamic disabling/help text
                date_help = "Search by date (YYYY-MM-DD or partial)."
                if only_web_selected: date_help += " (Not applicable if only Web is selected)"
                elif web_selected_with_others: date_help += " (Note: Does not apply to Web results)"
                
                date_search = st.text_input(
                    "Date", 
                    value=st.session_state.metadata_search.get("date", ""),
                    help=date_help, 
                    key=f"date_input_{st.session_state.metadata_form_key}",
                    disabled=only_web_selected
                )
                
            metadata_fuzzy = st.checkbox(
                "Enable fuzzy matching for metadata", 
                value=st.session_state.metadata_fuzzy,
                key=f"fuzzy_checkbox_{st.session_state.metadata_form_key}"
            )

        # --- Advanced Search Options ---
        col_adv1, col_adv2 = st.columns(2)
        with col_adv1:
            if internal_mode != "metadata_only":
                similarity = st.slider("Similarity Threshold", min_value=0.0, max_value=1.0, value=0.5, step=0.05,
                                       help="Minimum score for similarity results (content search)",
                                       key=f"similarity_slider_{st.session_state.metadata_form_key}")
            else: similarity = 0.5 # Default value when not shown
        with col_adv2:
            results_per_page = st.number_input("Results per page", min_value=5, max_value=50, value=10, step=5,
                                               key=f"results_per_page_{st.session_state.metadata_form_key}")

        # --- Submit Button ---
        search_submitted = st.form_submit_button("Search", on_click=handle_form_submission)
        
        # Store form data in session state when form is submitted
        if search_submitted:
            st.session_state.form_data = {
                "query": search_query,
                "title": title_search,
                "author": author_search if not only_web_selected else "",
                "publisher": publisher_search,
                "date": date_search if not only_web_selected else "",
                "fuzzy": metadata_fuzzy
            }

    # --- Handle Search Submission ---
    if st.session_state.form_submitted:
        st.session_state.form_submitted = False # Reset flag
        
        # Get values from form_data
        form_data = st.session_state.form_data
        search_query = form_data["query"]
        title_search = form_data["title"]
        author_search = form_data["author"]
        publisher_search = form_data["publisher"]
        date_search = form_data["date"]
        metadata_fuzzy = form_data["fuzzy"]
        
        # Log the current state for debugging
        logger.info(f"Processing form submission. Form data: {form_data}")

        # Validate inputs
        if not any(st.session_state.collection_selection.values()):
            st.warning("Please select at least one collection to search.")
        elif not search_query and not any([title_search, author_search, publisher_search, date_search]):
            st.warning("Please enter a search query or at least one metadata filter.")
        else:
            # Reset page number for new search
            st.session_state.search_page = 1
            
            # Store search query in session state
            st.session_state.search_query = search_query
            
            # Update metadata state
            st.session_state.metadata_search = {
                "title": title_search,
                "author": author_search,
                "publisher": publisher_search,
                "date": date_search,
            }
            st.session_state.metadata_fuzzy = metadata_fuzzy

            # Log the search parameters for debugging
            logger.info(f"Search parameters - Query: '{search_query}', Mode: '{internal_mode}'")
            logger.info(f"Metadata filters: {st.session_state.metadata_search}")
            logger.info(f"Collection filter: {get_collection_filter(st.session_state.collection_selection)}")

            # Prepare metadata dict for API call (only non-empty)
            metadata_api = {}
            if title_search: metadata_api["title"] = title_search
            if author_search: metadata_api["author"] = author_search
            if publisher_search: metadata_api["publisher"] = publisher_search
            if date_search: metadata_api["date"] = date_search

            # Get collection filter string
            collection_filter = get_collection_filter(st.session_state.collection_selection)

            # Perform search
            results = perform_search(
                query_rag_fn, query_metadata_fn, search_query,
                collection_filter,
                similarity,
                100, # Max results from backend
                metadata_api, metadata_fuzzy, internal_mode,
            )

            if results is not None: # Check for API error
                logger.info(f"Search returned {len(results)} results for mode '{internal_mode}' with filter '{collection_filter}'")
                st.session_state.search_results = results
                st.session_state.total_results = len(results)
            else: # API error occurred
                st.session_state.search_results = []
                st.session_state.total_results = 0

            st.rerun() # Rerun to display results or no results message

    # --- Display "New Search" Button ---
    if st.session_state.search_query or any(v for v in st.session_state.metadata_search.values() if v):
         st.button("✨ New Search", on_click=set_clear_search_flag,
                   key=f"clear_search_button_{st.session_state.metadata_form_key}",
                   help="Clear all search fields and results")

    # --- Display Search Results ---
    if st.session_state.search_results:
        search_type_executed = ""
        has_query = bool(st.session_state.search_query)
        has_metadata = any(v for v in st.session_state.metadata_search.values() if v)
        if has_query and has_metadata: search_type_executed = "Combined content and metadata search"
        elif has_query: search_type_executed = "Content-based search"
        elif has_metadata: search_type_executed = "Metadata-only search"
        st.info(f"{search_type_executed} returned {st.session_state.total_results} results")
        display_search_results(results_per_page) # Pass results_per_page from form
    elif st.session_state.search_query or any(v for v in st.session_state.metadata_search.values() if v):
        # Show 'no results' only if a search was attempted
        if st.session_state.search_results is None: # Check if API error occurred
             st.error("Search failed. Please check logs or try again.")
        else:
             st.info("No results found. Try adjusting your search terms or filters.")

    # --- Footer ---
    render_footer()


# --- perform_search function (Modified to fix metadata handling) ---
def perform_search(
    query_rag_fn,
    query_metadata_fn,
    query,
    collection_filter,
    similarity,
    max_results,
    metadata=None,
    metadata_fuzzy=True,
    search_mode="auto",
):
    """Query the RAG service with search parameters"""
    try:
        metadata = metadata or {} # Ensure metadata is a dict
        
        # Check if metadata has any non-empty values
        has_metadata_values = any(v for v in metadata.values() if v)
        
        # Log the decision factors for debugging
        logger.info(f"Search decision factors - Mode: {search_mode}, Query: {bool(query)}, Has metadata values: {has_metadata_values}")
        logger.info(f"Metadata content: {metadata}")

        # Determine which search function to use based on the search mode and available inputs
        if search_mode == "combined" and has_metadata_values and query and query_metadata_fn:
            # For combined search with both query and metadata, always use metadata endpoint
            logger.info(f"Using metadata search endpoint for combined search. Query: '{query}', Metadata: {metadata}")
            results = query_metadata_fn(
                metadata=metadata,
                query=query,
                top_k=max_results,
                collection_filter=collection_filter,
                metadata_fuzzy=metadata_fuzzy,
            )
        elif search_mode == "metadata_only" and has_metadata_values and query_metadata_fn:
            # For metadata-only search
            logger.info(f"Using metadata search endpoint for metadata-only search. Metadata: {metadata}")
            results = query_metadata_fn(
                metadata=metadata,
                query="",  # Empty query for metadata-only
                top_k=max_results,
                collection_filter=collection_filter,
                metadata_fuzzy=metadata_fuzzy,
            )
        elif search_mode == "content_only" and query and query_rag_fn:
            # For content-only search
            logger.info(f"Using content search endpoint for content-only search. Query: '{query}'")
            results = query_rag_fn(
                query=query,
                top_k=max_results,
                similarity_threshold=similarity,
                collection_filter=collection_filter,
                mode="combined",  # Default RAG mode
            )
        elif search_mode == "auto":
            # Auto-detect mode
            if has_metadata_values and query and query_metadata_fn:
                # Both query and metadata - use metadata endpoint
                logger.info(f"Auto-mode: Using metadata search endpoint. Query: '{query}', Metadata: {metadata}")
                results = query_metadata_fn(
                    metadata=metadata,
                    query=query,
                    top_k=max_results,
                    collection_filter=collection_filter,
                    metadata_fuzzy=metadata_fuzzy,
                )
            elif has_metadata_values and query_metadata_fn:
                # Only metadata - use metadata endpoint
                logger.info(f"Auto-mode: Using metadata-only search. Metadata: {metadata}")
                results = query_metadata_fn(
                    metadata=metadata,
                    query="",
                    top_k=max_results,
                    collection_filter=collection_filter,
                    metadata_fuzzy=metadata_fuzzy,
                )
            elif query and query_rag_fn:
                # Only query - use content endpoint
                logger.info(f"Auto-mode: Using content-only search. Query: '{query}'")
                results = query_rag_fn(
                    query=query,
                    top_k=max_results,
                    similarity_threshold=similarity,
                    collection_filter=collection_filter,
                    mode="combined",
                )
            else:
                logger.warning("Auto-mode: No valid search criteria provided")
                return []
        else:
            logger.warning(f"Could not determine appropriate search method for mode '{search_mode}'")
            st.warning("Could not perform search with the selected options.")
            return [] # Return empty list for unhandled cases

        # Log results count
        if results is not None:
            logger.info(f"Search API returned {len(results)} results")
        else:
            logger.warning("Search API returned None (indicating an error)")

        return results # Return results list or None

    except Exception as e:
        st.error(f"Error performing search: {str(e)}")
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Search error in perform_search: {error_trace}")
        return None # Indicate error with None


# --- display_search_results function (Unchanged) ---
def display_search_results(results_per_page):
    """Display paginated search results based on confirmed API structure."""
    total_results = st.session_state.total_results
    current_page = st.session_state.search_page
    results = st.session_state.search_results

    if not results: return # Exit if no results
    total_pages = math.ceil(total_results / results_per_page)
    # Ensure current_page is valid, correcting if necessary (e.g., if results per page changed)
    current_page = max(1, min(current_page, total_pages))
    st.session_state.search_page = current_page # Update state if corrected

    start_idx = (current_page - 1) * results_per_page
    end_idx = min(start_idx + results_per_page, total_results)

    st.markdown(f"**Showing results {start_idx + 1}-{end_idx} of {total_results}**")

    for i, result in enumerate(results[start_idx:end_idx]):
        current_result_index = start_idx + i
        if not isinstance(result, dict):
             logger.warning(f"Skipping invalid result item at index {current_result_index}: {result}")
             continue

        # --- Access Nested Metadata Directly ---
        metadata = result.get("metadata", {})
        if not isinstance(metadata, dict):
             logger.warning(f"Result {current_result_index} has invalid or missing metadata. Displaying minimal info.")
             metadata = {} # Use empty dict for safe gets

        # --- Get Core Fields (Top-Level) ---
        content = result.get("content", "") # Content is top-level
        score = result.get("score")         # Score is top-level
        doc_id = result.get("id", f"result_{current_result_index}") # ID is top-level

        # --- Get Fields from Metadata Dictionary ---
        doc_type_raw = metadata.get("doc_type", "unknown")
        doc_type = doc_type_raw.lower().strip()

        # Title logic: prefer subject, then title from metadata
        title = metadata.get("subject") # Check metadata dict
        if not title or title == "Unknown":
             title = metadata.get("title") # Check metadata dict
        # Final fallback if title/subject missing or default values found
        if not title or title in ["Unknown", "Untitled Document", "Untitled Web Page", "Email Subject Unknown", "Document Title Unknown", "Web Page Title Unknown"]:
             title = f"Result {current_result_index + 1}"

        meta_parts = []
        url = metadata.get("url", "#") # Get URL from metadata
        doc_filename = metadata.get("file_name")
        from shared.utils import make_prefixed_document_url

        # --- Display Type ---
        type_display = doc_type_raw.capitalize()
        if doc_type == "web": type_display = "Web Page"
        elif doc_type == "technical": type_display = "Document (Technical)" # Handle technical subtype if present
        elif doc_type == "unknown": type_display = "Unknown"
        # Add other explicit checks if needed (e.g., elif doc_type == "email": type_display = "Email")
        meta_parts.append(f"**Type**: {type_display}")

        # --- Add Fields Based on Type (from metadata dict) ---
        if doc_type == "email":
            date = metadata.get("date", "Unknown")
            sender = metadata.get("from", metadata.get("from_", "Unknown")) # Check both keys in metadata
            if date != "Unknown": meta_parts.append(f"**Date**: {date}")
            if sender != "Unknown": meta_parts.append(f"**From**: {sender}")
            if url != "#" and url != "Unknown": meta_parts.append(f"**Source**: [Link]({url})")

        elif doc_type == "document" or doc_type == "technical":
            date = metadata.get("publication_date", metadata.get("date", "Unknown")) # Check both keys in metadata
            author = metadata.get("author", "Unknown Author")
            publisher = metadata.get("publisher", "Unknown Publisher")
            if date != "Unknown": meta_parts.append(f"**Date**: {date}")
            if author != "Unknown Author": meta_parts.append(f"**Author**: {author}")
            if publisher != "Unknown Publisher": meta_parts.append(f"**Publisher**: {publisher}")

            # Position (from metadata)
            chunk_num = metadata.get("chunk_number")
            total_chunks = metadata.get("total_chunks")
            # Ensure both are numeric and total_chunks > 1
            if chunk_num is not None and total_chunks is not None:
                 try:
                     chunk_num_f = float(chunk_num); total_chunks_f = float(total_chunks)
                     if total_chunks_f > 1:
                         position_pct = round(((chunk_num_f -1) / total_chunks_f) * 10) * 10
                         position_text = f"{position_pct}%"
                         if position_pct == 0: position_text = "Beginning"
                         elif position_pct >= 90: position_text = "End"
                         meta_parts.append(f"**Position**: ~{position_text}")
                 except (ValueError, TypeError, ZeroDivisionError): pass # Ignore calculation errors

            # Always use normalized/prefixed filename for document/technical links
            if doc_filename:
                normalized_url = make_prefixed_document_url(doc_filename, "/download/pdf/")
                meta_parts.append(f"**Source**: [Link]({normalized_url})")
            elif url != "#" and url != "Unknown":
                meta_parts.append(f"**Source**: [Link]({url})")

        elif doc_type == "web":
            domain = metadata.get("domain", "")
            captured_at = metadata.get("captured_at", "")
            web_url = metadata.get("source_url") or url # Prefer source_url from metadata
            if domain: meta_parts.append(f"**Domain**: {domain}")
            if web_url != "#" and web_url != "Unknown":
                 meta_parts.append(f"**Source**: [Link]({web_url})")
                 url = web_url # Ensure button uses the best URL
            if captured_at: meta_parts.append(f"**Scanned**: {captured_at}")

            # Position (from metadata) - Copied from document block
            chunk_num = metadata.get("chunk_number")
            total_chunks = metadata.get("total_chunks")
            if chunk_num is not None and total_chunks is not None:
                 try:
                     chunk_num_f = float(chunk_num); total_chunks_f = float(total_chunks)
                     if total_chunks_f > 1:
                         position_pct = round(((chunk_num_f -1) / total_chunks_f) * 10) * 10
                         position_text = f"{position_pct}%"
                         if position_pct == 0: position_text = "Beginning"
                         elif position_pct >= 90: position_text = "End"
                         meta_parts.append(f"**Position**: ~{position_text}")
                 except (ValueError, TypeError, ZeroDivisionError): pass

        else: # Fallback for unknown type
            if url != "#" and url != "Unknown": meta_parts.append(f"**Source**: [Link]({url})")

        # --- Add Relevance Score (Conditional - from top level) ---
        if score is not None:
            try:
                score_value = float(score)
                if score_value >= MIN_SCORE_THRESHOLD:
                    meta_parts.append(f"**Relevance**: {score_value:.2f}")
            except (ValueError, TypeError): pass # Ignore non-numeric scores

        # --- Display Result ---
        st.markdown(f"### {current_result_index + 1}. {title}")
        if meta_parts:
            st.markdown(" | ".join(meta_parts))

        # Display content snippet (from top level)
        if not content:
            content = result.get("message", "") # Check legacy 'message' field
        if not content:
            st.info("No content snippet available for this result.")
        else:
            snippet = content[:500] + ("..." if len(content) > 500 else "")
            cleaned_snippet = " ".join(snippet.split()) # Basic whitespace cleanup
            st.code(cleaned_snippet, language=None)

        # Action button
        st.button("Ask about this", key=f"ask_{current_result_index}", on_click=set_prepared_question, args=(title,))

        # Separator
        st.markdown("<hr style='margin: 5px 0; border: 0; border-top: 1px solid #eee;'>", unsafe_allow_html=True)

    # --- Pagination Controls ---
    if total_pages > 1:
        st.markdown("---")
        cols_page = st.columns([1, 3, 1])
        with cols_page[0]:
            if current_page > 1: st.button("← Previous", on_click=decrement_page, key="prev_page")
        with cols_page[1]:
            st.markdown(f"<p style='text-align: center;'>Page {current_page} of {total_pages}</p>", unsafe_allow_html=True)
        with cols_page[2]:
            if current_page < total_pages: st.button("Next →", on_click=increment_page, key="next_page")

# --- Entry Point (if run directly, for testing - Unchanged) ---
if __name__ == "__main__":
    def mock_query_rag(*args, **kwargs): return []
    def mock_query_metadata(*args, **kwargs): return []
    st.set_page_config(layout="wide")
    display_search_page(mock_query_rag, mock_query_metadata)


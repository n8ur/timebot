# /usr/local/lib/timebot/lib/shared/whoosh_search_core.py

from typing import Dict, Any, List, Optional, Union, Tuple
from whoosh.index import open_dir, Index
from whoosh.qparser import (
    QueryParser, MultifieldParser, OrGroup, AndGroup, QueryParserError, Plugin
)
from whoosh.query import (
    Term, And, Or, Wildcard, Prefix, FuzzyTerm, TermRange
)
from whoosh.searching import Searcher
from whoosh.fields import TEXT, DATETIME, Schema # Import Schema
import os
import logging

# Add logger
logger = logging.getLogger(__name__)

# --- FuzzyTermPlugin Definition ---
class FuzzyTermPlugin(Plugin):
    """Adds fuzzy searching for single terms to the QueryParser."""
    def __init__(self, maxdist=1):
        self.maxdist = maxdist
        logger.debug(f"FuzzyTermPlugin initialized with maxdist={maxdist}")

    def term_query(self, parser: QueryParser, fieldname: str, text: str, **kwargs) -> Union[Term, FuzzyTerm]:
        """Replaces Term query with FuzzyTerm if plugin is active."""
        default_query = parser.term_query(fieldname, text, **kwargs)
        if isinstance(default_query, Term):
            logger.debug(f"FuzzyTermPlugin replacing Term with FuzzyTerm for field='{fieldname}', text='{text}'")
            boost = kwargs.get('boost', 1.0)
            return FuzzyTerm(fieldname, text, boost=boost, maxdist=self.maxdist)
        else:
            logger.debug(f"FuzzyTermPlugin not applying fuzzy to non-Term query: {default_query}")
            return default_query

# --- Basic Search (Marked as potentially deprecated) ---
def search_whoosh(
    index_dir: str, query_str: str, field: str = "content", limit: int = 10
) -> list:
    """
    Perform a basic search on the Whoosh index.
    *** DEPRECATED potentially: Prefer using metadata_search for more robust querying. ***

    Args:
        index_dir: Directory path for the Whoosh index
        query_str: Query string to search for
        field: Field to search in
        limit: Maximum number of results to return

    Returns:
        List of matching documents with normalized scores
    """
    logger.warning("Call to deprecated search_whoosh function. Consider using metadata_search.")
    logger.debug(f"Executing basic search_whoosh: index='{index_dir}', query='{query_str}', field='{field}'")
    ix = None
    results = []
    try:
        ix = open_dir(index_dir)
        with ix.searcher() as searcher:
            try:
                parser = QueryParser(field, ix.schema)
                query = parser.parse(query_str)
                logger.debug(f"Parsed basic query: {query}")
                search_results = searcher.search(query, limit=limit)

                if hasattr(search_results, 'max_score') and search_results.max_score:
                    max_score = search_results.max_score
                else:
                    max_score = 1.0
                    logger.debug("No max_score attribute or max_score is zero. Using default value 1.0")
                if max_score == 0:
                    max_score = 1.0

                for hit in search_results:
                    result = dict(hit)
                    result["score_raw"] = hit.score # Keep raw score
                    result["score_normalized"] = hit.score / max_score
                    result["score"] = hit.score / max_score # Use normalized as default 'score' for now
                    results.append(result)
                logger.debug(f"Basic search found {len(results)} results.")
            except Exception as e:
                logger.error(f"Error during basic search execution: {e}", exc_info=True)
                logger.error(f"Query attempted: {query_str}, Field: {field}")
    except Exception as e:
        logger.error(f"Failed to open index '{index_dir}' in search_whoosh: {e}", exc_info=True)
    finally:
        if ix:
            try: ix.close()
            except: pass

    return results

# --- Metadata Search (Core Function) ---
def metadata_search(
    index_dir: str,
    metadata_filters: Dict[str, Union[str, List[str], Tuple[str, str]]],
    query_str: str = None,
    content_fields: List[str] = None,
    limit: int = 10,
    sort_by: str = None,
    reverse: bool = False,
    fuzzy: bool = False, # Note: Fuzzy only applies to query_str now
    fuzzy_maxdist: int = 2, # Only applies to query_str
    collection_type: str = None # Informational, used in result dict
) -> List[Dict[str, Any]]:
    """
    Perform a search focused on metadata fields with optional content search.
    Uses QueryParser for single string metadata filters for better handling
    of multi-word values and analyzers. Adds 'doc_type' to results.

    Args:
        index_dir: Directory path for the Whoosh index
        metadata_filters: Dictionary mapping field names to search values:
            - str: Parsed using QueryParser (handles multi-word, uses AND).
                   NOTE: Fuzzy matching is NOT applied to these string filters.
            - List[str]: Match any of the values (OR), each value parsed.
            - Tuple[str, str]: Range search (assumes lexicographical text dates
                               or specific date field handling). Use None for open ends.
        query_str: Optional content query string (fuzzy applies here if set).
        content_fields: Fields to search for query_str (defaults to "content").
        limit: Maximum number of results to return
        sort_by: Field to sort results by
        reverse: Whether to reverse the sort order
        fuzzy: Whether to use fuzzy matching *for the main query_str*.
        fuzzy_maxdist: Max edit distance for fuzzy matching *on query_str*.
        collection_type: Optional type indicator added to result dictionaries.

    Returns:
        List of matching documents as dictionaries, including 'doc_type'.
    """
    logger.debug(f"Initiating metadata_search in index: {index_dir}")
    logger.debug(f"Metadata Filters: {metadata_filters}")
    logger.debug(f"Query String: {query_str}, Fuzzy (for query_str): {fuzzy}")

    ix = None # Initialize ix to None
    searcher = None # Initialize searcher to None
    results = []
    final_query = None

    try:
        # Check if index exists before opening
        if not os.path.exists(index_dir) or not os.listdir(index_dir):
             logger.error(f"Whoosh index directory not found or empty: {index_dir}")
             return []
        ix = open_dir(index_dir)
        searcher = ix.searcher()
        schema = ix.schema # Get schema for field checks and parsers

        # --- Process metadata filters ---
        filter_queries = [] # Collect individual valid filter queries
        if metadata_filters: # Process only if filters are provided
            for field, value in metadata_filters.items():
                field_query = None # Query for the current field

                # Check if field exists in schema
                if field not in schema:
                    logger.warning(f"Metadata field '{field}' not found in schema for index {index_dir}. Skipping filter.")
                    continue

                try:
                    # --- Handle different value types ---
                    if isinstance(value, tuple) and len(value) == 2:
                        # Date/Term range: Use TermRange.
                        start_val = str(value[0]) if value[0] is not None else None
                        end_val = str(value[1]) if value[1] is not None else None
                        field_query = TermRange(field, start_val, end_val, inclusive_start=True, inclusive_end=True)
                        logger.debug(f"Created TermRange query for field '{field}': [{start_val} to {end_val}]")

                    elif isinstance(value, list):
                        # OR list of values: Parse each value using QueryParser
                        subqueries = []
                        parser = QueryParser(field, schema)
                        for item in value:
                            item_str = str(item).strip() # Ensure string and strip whitespace
                            if item_str: # Skip empty strings in list
                                try:
                                    parsed_item_query = parser.parse(item_str)
                                    subqueries.append(parsed_item_query)
                                except QueryParserError as list_parse_e:
                                    logger.warning(f"Could not parse list item '{item_str}' for field '{field}': {list_parse_e}. Skipping item.")
                            else:
                                logger.debug(f"Skipping empty item in list for field '{field}'.")

                        if subqueries:
                            field_query = Or(subqueries)
                            logger.debug(f"Created OR query for field '{field}' with {len(subqueries)} subqueries.")
                        else:
                            logger.warning(f"No valid subqueries generated for list filter on field '{field}'.")
                            field_query = None # No valid items

                    elif isinstance(value, str):
                        # Single string value: Use QueryParser for the specific field.
                        value_str = value.strip()
                        if value_str: # Skip empty strings
                            parser = QueryParser(field, schema)
                            try:
                                field_query = parser.parse(value_str)
                                logger.debug(f"Created QueryParser query for field '{field}' with value '{value_str}' -> {field_query}")
                            except QueryParserError as parse_e:
                                logger.warning(f"Could not parse metadata value '{value_str}' for field '{field}': {parse_e}. Skipping filter.")
                                field_query = None # Skip this filter if parsing fails
                        else:
                            logger.debug(f"Skipping empty string filter for field '{field}'.")
                            field_query = None

                    else:
                        # Handle potential other types or log a warning
                        logger.warning(f"Unsupported type for metadata filter value: {type(value)} for field '{field}'. Skipping.")
                        field_query = None

                    # Add the generated query for this field to our list if valid
                    if field_query is not None:
                        filter_queries.append(field_query)

                except Exception as field_proc_e:
                    logger.error(f"Error processing filter for field '{field}' with value '{value}': {field_proc_e}", exc_info=True)
                    # Continue to next field

        # Combine all valid metadata filter queries using AND
        if filter_queries:
            if len(filter_queries) == 1:
                final_query = filter_queries[0]
            else:
                final_query = And(filter_queries)
            logger.debug(f"Combined {len(filter_queries)} metadata filters into query: {final_query}")
        else:
            logger.debug("No valid metadata filters were provided or processed.")
            # final_query remains None

        # --- Add content search if provided ---
        if query_str:
            content_query_str = query_str.strip()
            if content_query_str: # Proceed only if query_str is not empty
                if not content_fields:
                    content_fields = ["content"] # Default content field
                # Ensure content fields exist in schema
                valid_content_fields = [cf for cf in content_fields if cf in schema]
                if not valid_content_fields:
                     logger.error(f"None of the specified content fields {content_fields} exist in the schema. Ignoring content query.")
                else:
                    logger.debug(f"Adding content query for fields {valid_content_fields} with query: '{content_query_str}'")
                    content_parser = MultifieldParser(valid_content_fields, schema)

                    # Apply fuzzy matching to the content query string if requested
                    if fuzzy:
                        try:
                            # Enable fuzzy terms in the parser
                            content_parser.add_plugin(FuzzyTermPlugin(maxdist=fuzzy_maxdist))
                            logger.debug(f"Enabled FuzzyTermPlugin (maxdist={fuzzy_maxdist}) for content query parser.")
                        except Exception as plugin_e:
                             logger.error(f"Failed to add FuzzyTermPlugin: {plugin_e}", exc_info=True)
                             # Continue without fuzzy plugin if it fails

                    try:
                        content_query = content_parser.parse(content_query_str)
                        logger.debug(f"Parsed content query: {content_query}")

                        # Combine with existing metadata query (if any) using AND
                        if final_query is None:
                            final_query = content_query
                        else:
                            # Combine using AND
                            final_query = And([final_query, content_query])
                        logger.debug(f"Combined content query. Final query is now: {final_query}")

                    except QueryParserError as content_parse_e:
                        logger.error(f"Could not parse content query string '{content_query_str}': {content_parse_e}. Content query ignored.")
                    except Exception as content_proc_e:
                        logger.error(f"Error processing content query '{content_query_str}': {content_proc_e}", exc_info=True)
            else:
                 logger.debug("Content query string is empty. Ignoring content search.")


        # If no query was built at all, match everything
        if final_query is None:
            logger.warning("No valid query could be constructed. Matching all documents.")
            # Use a wildcard query that matches everything
            indexed_fields = [name for name, field in schema.items() if field.indexed]
            if indexed_fields:
                # Prefer doc_id if available and indexed
                match_all_field = "doc_id" if "doc_id" in indexed_fields else indexed_fields[0]
                final_query = Wildcard(match_all_field, "*")
                logger.debug(f"Using wildcard query on field '{match_all_field}' to match all.")
            else:
                logger.error("Cannot construct 'match all' query: No indexed fields found in schema.")
                # Ensure cleanup happens before returning empty list
                if searcher: searcher.close()
                if ix: ix.close()
                return [] # Cannot search

        # --- Execute search ---
        try:
            kwargs = {"limit": limit}
            if sort_by:
                # Check if sort_by field exists and is sortable
                if sort_by in schema and schema[sort_by].sortable:
                    kwargs["sortedby"] = sort_by
                    kwargs["reverse"] = reverse
                    logger.debug(f"Executing search with sorting: field='{sort_by}', reverse={reverse}")
                else:
                    logger.warning(f"Sort field '{sort_by}' not found in schema or not sortable. Ignoring sorting.")

            logger.info(f"Executing final search query: {final_query} with limit={limit}, kwargs={kwargs}")
            search_results = searcher.search(final_query, **kwargs)

            # Convert results to dictionaries and add score/collection_type/doc_type
            for hit in search_results:
                result_dict = dict(hit)
                result_dict["score"] = hit.score # Use raw Whoosh score

                # *** ADD doc_type BASED ON collection_type ***
                if collection_type:
                    result_dict["doc_type"] = collection_type # Add the doc_type field
                    # result_dict["collection_type"] = collection_type # Optional: Keep original key if needed elsewhere
                    # Add search_provider based on collection_type
                    result_dict["search_provider"] = f"Whoosh-{collection_type.capitalize()}"
                else:
                    # If collection_type wasn't passed (shouldn't happen with current wrappers), default
                    result_dict["doc_type"] = "unknown"
                    result_dict["search_provider"] = "Whoosh-Unknown"

                results.append(result_dict)

            logger.info(f"Search completed. Found {len(results)} raw results.")

        except Exception as search_e:
            logger.error(f"Error during Whoosh search execution: {search_e}", exc_info=True)
            logger.error(f"Query attempted: {final_query}")

    except Exception as e:
        # Catch errors during index opening or initial setup
        logger.error(f"Failed during Whoosh metadata_search setup: {e}", exc_info=True)
        # Ensure cleanup happens even if setup fails
        if searcher:
            try: searcher.close()
            except: pass # Ignore errors during close if already in error state
        if ix:
            try: ix.close()
            except: pass
        return [] # Return empty list on setup failure

    finally:
        # Ensure searcher and index are closed if they were opened
        if searcher:
            try:
                searcher.close()
                logger.debug("Whoosh searcher closed.")
            except Exception as close_e:
                logger.error(f"Error closing Whoosh searcher: {close_e}")
        if ix:
             try:
                 ix.close()
                 logger.debug("Whoosh index object closed.")
             except Exception as close_e:
                 logger.error(f"Error closing Whoosh index object: {close_e}")

    # Return the list of result dictionaries
    return results


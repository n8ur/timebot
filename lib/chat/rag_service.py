# /usr/local/lib/timebot/lib/chat/rag_service.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import requests
import json
import streamlit as st
import datetime
import logging
import re
from typing import Dict, Any, List, Optional

from shared.config import config
# Use config["config["EMBEDDING_SERVER_URL"]"], etc. directly below.

from chat.prompts import SYSTEM_PROMPT, LLM_ENHANCEMENT_PROMPT

import chat.rag_enhancement # For LLM-based query enhancement
import chat.llm_service     # To pass llm_service.query_llm as a callable

logger = logging.getLogger(__name__)


def determine_query_type(conversation_history: List[Dict[str, Any]]) -> str:
    """
    Determine if the current query is a follow-up or a new topic using improved detection.
    Assumes `conversation_history` includes the current user query as the last relevant message.
    """
    if not conversation_history:
        logger.debug("RAG CONTEXT - Query classified as new topic (no conversation history)")
        return "new_topic"

    user_messages_content = [msg["content"] for msg in conversation_history if msg["role"] == "user"]

    if len(user_messages_content) < 2:
        # Needs at least current user query and one previous user query to compare or check context.
        logger.debug(
            "RAG CONTEXT - Query classified as new topic (insufficient user message history for follow-up detection - need >= 2)."
            f" Found {len(user_messages_content)} user messages."
        )
        return "new_topic"

    last_query_content = user_messages_content[-1] # Current query
    prev_query_content = user_messages_content[-2] # Previous user query

    # 1. Check linguistic indicators in the current query
    follow_up_indicators = [
        "what about", "how about", "can you", "please explain", "tell me more",
        "why", "how", "when", "where", "who", "could you", "would you", "?",
        "explain", "and", "also", "additionally", "furthermore", "moreover", "besides",
    ]
    for indicator in follow_up_indicators:
        if last_query_content.lower().startswith(indicator):
            logger.debug(
                "RAG CONTEXT - Follow-up detected by linguistic indicator:"
                f" '{indicator}' in query '{last_query_content[:50]}...'"
            )
            return "follow_up"

    # 2. Check for pronouns in the current query
    reference_pronouns = [
        r"\bit\b", r"\bthis\b", r"\bthat\b", r"\bthese\b", r"\bthose\b",
        r"\bhe\b", r"\bshe\b", r"\bthey\b", r"\bthem\b", r"\btheir\b",
    ]
    for pronoun_regex in reference_pronouns:
        if re.search(pronoun_regex, last_query_content.lower()):
            logger.debug(
                "RAG CONTEXT - Follow-up detected by pronoun reference:"
                f" '{pronoun_regex}' in query '{last_query_content[:50]}...'"
            )
            return "follow_up"

    # 3. Check topic similarity if a previous user query exists (which it does if we reach here)
    def extract_keywords(text: str) -> List[str]:
        text_cleaned = re.sub(r"[^\w\s]", "", text.lower())
        return [word for word in text_cleaned.split() if len(word) >= 4]

    last_keywords = extract_keywords(last_query_content)
    prev_keywords = extract_keywords(prev_query_content)

    if last_keywords and prev_keywords:
        common_keywords = set(last_keywords).intersection(set(prev_keywords))
        overlap_count = len(common_keywords)
        min_len = min(len(last_keywords), len(prev_keywords)) # Avoid division by zero
        overlap_percentage = (overlap_count / min_len) if min_len > 0 else 0

        if overlap_count >= 2 or overlap_percentage >= 0.3:
            logger.debug(
                "RAG CONTEXT - Follow-up detected by keyword overlap:"
                f" {overlap_count} common keywords, {overlap_percentage:.2f} overlap."
                f" Last: '{last_query_content[:50]}...', Prev: '{prev_query_content[:50]}...'"
            )
            return "follow_up"

    logger.debug(f"RAG CONTEXT - Query classified as new topic: '{last_query_content[:50]}...'")
    return "new_topic"


# RENAMED: This function was previously 'enhance_follow'. Renamed to 'enhance_query' for clarity.
def enhance_query(
    query_to_enhance: str, conversation_history: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Enhance a follow-up query with context from previous conversation turns (rule-based).
    `query_to_enhance` is the query to potentially enhance (could be original or LLM-enhanced).
    `conversation_history` includes the current query. This function needs to find the *previous* user query.
    """
    logger.debug(f"Starting RULE-BASED enhancement of query: '{query_to_enhance}'")

    enable_enhancement = st.session_state.get(
        "enable_query_enhancement", config["ENABLE_RULE_BASED_ENHANCEMENT"]
    )
    if not enable_enhancement:
        logger.debug("Rule-based enhancement disabled in settings (session/default).")
        return query_to_enhance

    if not conversation_history:
        logger.debug("No conversation history provided for rule-based enhancement.")
        return query_to_enhance

    try:
        # Extract all user queries from the history.
        all_user_queries_in_history = [
            msg["content"] for msg in conversation_history if msg["role"] == "user"
        ]

        previous_query_content = None
        if len(all_user_queries_in_history) >= 2:
            # The `query_to_enhance` is the current query being processed.
            # The last user query in `all_user_queries_in_history` should match `query_to_enhance`.
            # The one before that is the "previous_query_content" we need for context.
            if all_user_queries_in_history[-1].strip().lower() == query_to_enhance.strip().lower():
                previous_query_content = all_user_queries_in_history[-2]
            else:
                # This might happen if query_to_enhance was already modified by LLM stage
                # and doesn't exactly match the last user message.
                # A more robust way is to assume the last entry in all_user_queries_in_history
                # IS the current query contextually, and the one before is previous.
                logger.debug(
                    "'query_to_enhance' param did not exactly match "
                    "the last user message in history. Using second-to-last user message as context."
                )
                previous_query_content = all_user_queries_in_history[-2] # Still take the one before last
        else: # Not enough user queries for a "previous" one.
            logger.debug("Not enough user queries in history for rule-based context (need >= 2).")
            return query_to_enhance


        if not previous_query_content:
            logger.debug("No previous user query found for rule-based enhancement context.")
            return query_to_enhance

        logger.debug(f"Previous user query for rule-based context: '{previous_query_content}'")

        is_short_query = len(query_to_enhance.split()) <= 5
        has_pronoun = re.search(r'\b(it|this|that|these|those|they|them|their)\b', query_to_enhance.lower())

        if is_short_query or has_pronoun:
            logger.debug(
                f"ENHANCE DEBUG - Query qualifies for rule-based enhancement: "
                f"short={is_short_query}, has_pronoun={has_pronoun is not None}"
            )

            cleaned_previous_query = re.sub(r'[^\w\s]', ' ', previous_query_content.lower())
            words = cleaned_previous_query.split()

            stopwords = [
                'what', 'when', 'where', 'which', 'why', 'how', 'can', 'does',
                'will', 'should', 'would', 'could', 'from', 'with', 'about',
                'the', 'and', 'for', 'this', 'that', 'these', 'those', 'is', 'are'
            ]

            technical_terms = []
            # Extract multi-word technical terms
            for i in range(len(words) - 1):
                if (len(words[i]) >= 3 and len(words[i+1]) >= 3 and
                    words[i] not in stopwords and words[i+1] not in stopwords):
                    technical_terms.append(f"{words[i]} {words[i+1]}")

            # If not enough multi-word terms, try single significant words
            if len(technical_terms) < 2:
                for word in words:
                    if (len(word) >= 4 and word not in stopwords and
                        word not in ' '.join(technical_terms)): # Avoid duplicates
                        technical_terms.append(word)
                        if len(technical_terms) >= 2: # Limit to 2 terms overall
                            break
            
            technical_terms = technical_terms[:2] # Ensure max 2 terms

            if technical_terms:
                terms_str = ", ".join(technical_terms)
                rule_enhanced_output_str = ""
                if has_pronoun:
                    rule_enhanced_output_str = f"{query_to_enhance} (regarding {terms_str})"
                else: # For short queries without pronouns
                    rule_enhanced_output_str = f"{query_to_enhance} (in the context of {terms_str})"

                logger.info(f"Follow-up query enhanced to: '{rule_enhanced_output_str}'")
                return rule_enhanced_output_str
            else:
                logger.debug("No usable technical terms found for rule-based enhancement.")
        else:
            logger.debug("Query does not qualify for rule-based enhancement (not short, no pronoun).")

        logger.debug("No rule-based enhancement applied to query.")
        return query_to_enhance

    except Exception as e:
        logger.error(f"ENHANCE DEBUG - Error in rule-based enhancing query: {str(e)}", exc_info=True)
        return query_to_enhance # Fallback to the query that was passed in


def query_rag(
    query: str, # This is the original user query from the UI
    top_k: int = config["TOP_K"],
    similarity_threshold: float = config["SIMILARITY_THRESHOLD"],
    collection_filter: str = "all",
    mode: str = "combined",
    conversation_history: Optional[List[Dict[str, Any]]] = None, # Includes `query` as last user message
) -> List[Dict[str, Any]]:
    """
    Query the RAG API. Enhances query via LLM then rule-based (if applicable).
    Uses cache. Updates cache with detailed enhancement info.
    """
    user_id = None
    if conversation_history and conversation_history[-1].get("user_id"):
        user_id = conversation_history[-1]["user_id"]
    logger.info(f"RAG QUERY - user_id={user_id} original_query=\"{query}\" top_k={top_k} similarity_threshold={similarity_threshold} collection_filter={collection_filter} mode={mode}")
    logger.debug(f"Entered rag_service.query_rag with original query: '{query[:100]}...'")

    original_query = query
    query_for_processing = original_query # This variable will be transformed through stages

    llm_actually_changed_query = False
    rule_actually_changed_query = False
    query_after_llm_stage = original_query # Initialize to original

    # `conversation_history` (if provided) includes the current `original_query` as the last user message.
    # This full history is suitable for `determine_query_type` and `enhance_query` (rule-based).
    history_for_context_funcs = conversation_history if conversation_history else []

    try:
        # Step 1: Determine query type (e.g., follow-up) using full history
        query_type = "new_topic"
        if history_for_context_funcs: # determine_query_type handles internal checks for length
            query_type = determine_query_type(history_for_context_funcs)
        logger.debug(f"Query type determined as: {query_type}")


        # Step 2: LLM-based Query Enhancement (if enabled globally)
        if config["ENABLE_LLM_QUERY_ENHANCEMENT"]:
            logger.debug(f"Attempting LLM query enhancement for: '{query_for_processing}'")
            # History for LLM enhancer: all messages *before* the current original_query.
            # The `enhance_follow-up_query_with_llm` function itself doesn't use conversation_history
            # to construct its prompt in the current `rag_enhancement.py` version,
            # but passing it for future flexibility or if that function changes.
            history_for_llm_enhancer = []
            if history_for_context_funcs:
                # Find the index of the current query if it's the last user message
                # This assumes original_query is indeed the content of the last user message.
                idx_current_query = -1
                for i in range(len(history_for_context_funcs) - 1, -1, -1):
                    if history_for_context_funcs[i]["role"] == "user" and \
                       history_for_context_funcs[i]["content"].strip() == original_query.strip():
                        idx_current_query = i
                        break
                if idx_current_query != -1:
                    history_for_llm_enhancer = history_for_context_funcs[:idx_current_query]
                else: # Fallback: if current query not found as last user message, pass all history (enhancer might ignore)
                    history_for_llm_enhancer = history_for_context_funcs
                    logger.debug("Could not definitively isolate history before current query for LLM enhancer.")


            # IMPORTANT: Use enhance_query_with_llm (not enhance_follow-up_query_with_llm) from rag_enhancement.
            # This is the correct function for LLM-based query enhancement. Do NOT revert this!
            llm_enhanced_output = chat.rag_enhancement.enhance_query_with_llm(
                original_query=query_for_processing, # Pass current state of query
                conversation_history=history_for_llm_enhancer,
                llm_querier=chat.llm_service.query_llm,
                enable_llm_enhancement=True, # Already guarded by outer if
                enhancement_prompt_template=LLM_ENHANCEMENT_PROMPT,
                enhancement_model=config["LLM_ENHANCEMENT_MODEL"],
            )
            query_after_llm_stage = llm_enhanced_output # Store result of LLM stage

            if llm_enhanced_output.strip().lower() != query_for_processing.strip().lower():
                logger.debug( f"Query LLM-enhanced: '{query_for_processing}' -> '{llm_enhanced_output}'")
                query_for_processing = llm_enhanced_output # Update for next stage
                llm_actually_changed_query = True
            else:
                logger.debug("LLM enhancement made no textual change or returned original query")
        else:
            query_after_llm_stage = original_query # No LLM enhancement applied
            logger.debug("LLM query enhancement is disabled by global configuration.")

        # Step 3: Rule-based Enhancement (if enabled by UI toggle AND query is follow-up)
        # This operates on `query_for_processing` (which might be LLM-enhanced or original)
        final_query_for_rag = query_for_processing

        enable_rule_based_ui_toggle = st.session_state.get(
            "enable_query_enhancement", config["ENABLE_RULES_QUERY_ENHANCEMENT"]
        )
        logger.debug(
            f"Rule-based follow-up enhancement UI toggle: {enable_rule_based_ui_toggle}")

        if enable_rule_based_ui_toggle and query_type == "follow_up":
            logger.debug(f"Calling rule-based enhanced query for follow-up question on: '{query_for_processing}'")
            # `enhance_query` (rule-based) needs full history (including current query)
            # to correctly identify the *previous* user query for context.
            rule_enhanced_output = enhance_query(
                query_for_processing, history_for_context_funcs # Pass full history
            )
            if rule_enhanced_output.strip().lower() != query_for_processing.strip().lower():
                logger.debug("Query was rule-enhanced (for follow-up): "
                    f"'{query_for_processing}' -> '{rule_enhanced_output}'")
                final_query_for_rag = rule_enhanced_output
                rule_actually_changed_query = True
            else:
                logger.debug("Rule-based enhancement made NO textual change to follow-up query")
                # final_query_for_rag remains query_for_processing
        else:
            if query_type != "follow_up":
                logger.debug("Rule-based enhancement skipped: not a follow-up query.")
            if not enable_rule_based_ui_toggle:
                logger.debug("Rule-based enhancement skipped: disabled by UI toggle.")
            # final_query_for_rag remains query_for_processing

        logger.debug(
            f"Final query for RAG API call: '{final_query_for_rag}'"
            f" (Original user query: '{original_query}')"
        )

        # Step 4: Cache Logic
        use_cache = False
        cache_entry_results = None # Store only results if cache hit
        if "rag_cache" in st.session_state and st.session_state.rag_cache.get("results") is not None:
            cached_data = st.session_state.rag_cache
            cache_is_fresh = cached_data.get("timestamp") and \
               ((datetime.datetime.now() - cached_data["timestamp"]).total_seconds() < 300) # 5 mins

            if cache_is_fresh:
                if cached_data.get("original_query") == original_query and \
                   cached_data.get("final_query_for_rag") == final_query_for_rag:
                    logger.debug("Cache HIT: Valid (original and final RAG query match).")
                    use_cache = True
                    cache_entry_results = cached_data.get("results", [])
                elif cached_data.get("original_query") == original_query:
                    logger.debug(
                        "Cache MISS: Original query matches, but final RAG query differs. "
                        f"Old final: '{cached_data.get('final_query_for_rag')}', New final: '{final_query_for_rag}'. "
                        "Invalidating."
                    )
                else:
                    logger.debug("Cache MISS: Original query differs. Invalidating.")
            else:
                logger.debug("Cache MISS: Stale (expired).")
        else:
            logger.debug("Cache MISS: No existing cache or no results in cache.")

        results_from_rag_api = []
        if use_cache and cache_entry_results is not None:
            logger.debug("Using cached RAG results.")
            results_from_rag_api = cache_entry_results
        else:
            logger.debug(
                f"Executing new RAG search with query: '{final_query_for_rag}'"
            )
            endpoint = "/api/query"
            full_url = f"{config['EMBEDDING_SERVER_URL']}:{config['EMBEDDING_SERVER_PORT']}{endpoint}"
            payload = {
                "query": final_query_for_rag,
                "similarity_threshold": similarity_threshold,
                "top_k": top_k,
                "use_reranking": True,
                "mode": mode,
                "collection_filter": collection_filter,
                "fuzzy": True,
            }
            logger.debug(f"Payload to RAG API: {json.dumps(payload)}")

            response = requests.post(full_url, json=payload)
            response.raise_for_status()
            result_json = response.json()

            if isinstance(result_json, dict) and "results" in result_json:
                results_from_rag_api = result_json["results"]
                logger.info(f"RAG API returned {len(results_from_rag_api)} results.")
            else:
                logger.warning(f" Unexpected RAG API response format: {type(result_json)}. Content: {str(result_json)[:200]}")
                results_from_rag_api = []

            # Update cache with new search results and detailed enhancement info
            st.session_state.rag_cache = {
                "original_query": original_query,
                "query_after_llm_enhancement": query_after_llm_stage,
                "final_query_for_rag": final_query_for_rag,
                "llm_enhancement_applied_flag": llm_actually_changed_query,
                "rule_enhancement_applied_flag": rule_actually_changed_query,
                "results": results_from_rag_api, # Store the actual results
                "timestamp": datetime.datetime.now(),
                "last_query": original_query, # For backward compatibility
                "enhanced_query": final_query_for_rag, # For backward compatibility
            }
            logger.debug(
                f"Updated cache. Original: '{original_query}', "
                f"LLM changed: {llm_actually_changed_query} (to '{query_after_llm_stage}'), "
                f"Rule changed: {rule_actually_changed_query} (final: '{final_query_for_rag}')"
            )

        if final_query_for_rag.strip().lower() != original_query.strip().lower():
             logger.debug(
                 f"FINAL CHECK: Original query '{original_query}' was enhanced to '{final_query_for_rag}' for RAG."
             )
        else:
            logger.debug(
                 f"FINAL CHECK: Original query '{original_query}' was used for RAG without textual change from enhancements."
            )

        return results_from_rag_api if results_from_rag_api is not None else []

    except requests.exceptions.RequestException as e:
        error_msg = f"RAG query failed due to a network or API error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None
    except Exception as e:
        error_msg = f"An unexpected error occurred during RAG query processing: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None



def clear_rag_cache():
    """Clear the RAG cache to force a new search on the next query.
    Uses the new detailed cache structure.
    """
    if "rag_cache" in st.session_state:
        st.session_state.rag_cache = {
            "original_query": None,
            "query_after_llm_enhancement": None,
            "final_query_for_rag": None,
            "llm_enhancement_applied_flag": False,
            "rule_enhancement_applied_flag": False,
            "results": None, # Explicitly set to None
            "timestamp": None,
            "last_query": None,
            "enhanced_query": None,
        }
        logger.debug("RAG cache cleared manually (new structure).")
        return True
    logger.debug("Attempted to clear RAG cache, but no cache found in session_state.")
    return False


def query_metadata( # Original function
    metadata: Dict[str, str],
    query: str = "",
    top_k: int = config["TOP_K"],
    collection_filter: str = "all",
    metadata_fuzzy: bool = True,
    metadata_threshold: float = 0.8,
) -> Optional[List[Dict[str, Any]]]:
    """
    Query the RAG API's metadata search endpoint.
    """
    logger.debug("--- Entered rag_service.query_metadata ---")
    try:
        endpoint = "/api/metadata_search"
        base_url = config['EMBEDDING_SERVER_URL']
        if not base_url.startswith(('http://', 'https://')):
            base_url = f"http://{base_url}"
        full_url = f"{base_url}:{config['EMBEDDING_SERVER_PORT']}{endpoint}"

        payload = {
            "metadata": {
                k: v for k, v in metadata.items() if v
            },
            "top_k": top_k,
            "metadata_fuzzy": metadata_fuzzy,
            "metadata_threshold": metadata_threshold,
            "collection_filter": collection_filter,
        }

        if query:
            payload["query"] = query

        logger.debug(f"METADATA SEARCH REQUEST - Payload: {json.dumps(payload)}")

        response = requests.post(full_url, json=payload)
        response.raise_for_status()

        result = response.json()

        if isinstance(result, dict) and "results" in result:
            results = result.get("results", [])
            logger.debug(
                "METADATA SEARCH RESPONSE - Received" f" {len(results)} results"
            )
            return results
        else:
            logger.warning(
                "Unexpected response format from metadata search:" f" {type(result)}"
            )
            logger.warning(f"Response sample: {str(result)[:500]}...")
            return []

    except requests.exceptions.RequestException as e:
        error_msg = "Error communicating with metadata search endpoint:" f" {str(e)}"
        logger.error(error_msg)
        st.error(error_msg)
        return None
    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Error parsing metadata search response: {str(e)}"
        logger.error(error_msg)
        st.error(error_msg)
        return None
    except Exception as e:
        error_msg = "An unexpected error occurred during metadata search:" f" {str(e)}"
        logger.error(error_msg, exc_info=True)
        st.error(error_msg)
        return None



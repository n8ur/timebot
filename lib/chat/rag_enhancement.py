# /usr/local/lib/timebot/lib/chat/rag_enhancement.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import logging
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)


def _construct_enhancement_prompt(
    original_query: str,
    prompt_template: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Constructs the prompt to be sent to the LLM for query enhancement.
    """
    # Basic template usage. You can make this more sophisticated,
    # e.g., by conditionally adding conversation history to the prompt.
    # For example, if history is relevant:
    # history_context = ""
    # if conversation_history:
    #     # Process history into a string format suitable for the prompt
    #     processed_history = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history[-3:]])
    #     (last 3 turns)
    #     history_context = f"Consider the following conversation history:\n{processed_history}\n\n"
    #
    # prompt = prompt_template.format(history=history_context, query=original_query)

    prompt = prompt_template.format(query=original_query)
    logger.debug("Constructed LLM enhancement prompt: [PROMPT_CONTENT_OMITTED] (see LLM_ENHANCEMENT_PROMPT)")
    return prompt


def enhance_query_with_llm(
    original_query: str,
    conversation_history: Optional[List[Dict[str, Any]]],
    # Pass the query_llm function from llm_service to avoid circular imports
    # and allow rag_service to control which LLM function is used.
    llm_querier: Callable[
        [str, Optional[str], Optional[List[Dict[str, Any]]], Optional[str]],
        Optional[str],
    ],
    # Configurations passed from chat_config or st.session_state
    enable_llm_enhancement: bool,
    enhancement_prompt_template: str,
    enhancement_model: Optional[str] = None, # Optional: if you want to specify a model for this task
) -> str:
    """
    Enhances the user's query using an LLM for potentially better RAG results.

    Args:
        original_query: The user's original query.
        conversation_history: The history of the conversation for context.
        llm_querier: A callable function (e.g., llm_service.query_llm)
                     that takes (prompt, model, context, conversation_history, user_id)
                     and returns the LLM's response string or None.
        enable_llm_enhancement: Boolean flag to enable/disable this feature.
        enhancement_prompt_template: The prompt template to use for enhancement.
        enhancement_model: Specific model to use for enhancement (optional).

    Returns:
        The LLM-enhanced query, or the original query if enhancement is
        disabled, fails, or is deemed unnecessary.
    """
    if not enable_llm_enhancement:
        logger.debug(
            "LLM-based query enhancement is disabled. Returning original query."
        )
        return original_query

    if not original_query or original_query.strip() == "":
        logger.debug("Original query is empty. Skipping LLM enhancement.")
        return original_query

    logger.info(
        f"Attempting LLM-based enhancement for query: '{original_query}'"
    )

    try:
        # 1. Construct the prompt for the LLM.
        #    You might want to add more sophisticated logic here, e.g.,
        #    only enhance if the query is short, or if it contains pronouns,
        #    or based on conversation history.
        prompt_for_llm = _construct_enhancement_prompt(
            original_query, enhancement_prompt_template, conversation_history
        )

        # 2. Call the LLM using the provided llm_querier function.
        #    Note: The `context` argument for `llm_querier` is typically RAG context.
        #    For query enhancement, we usually don't have RAG context yet.
        #    The `conversation_history` for `llm_querier` might be different
        #    from the one used for prompt construction if the LLM needs it in a specific format.
        #    Here, we pass None for RAG context and the original conversation_history.
        #    The `user_id` is also passed as None for now, adjust if needed.
        logger.debug(
            f"Calling LLM for query enhancement with model: {enhancement_model or 'default'}"
        )
        enhanced_query_llm_response = llm_querier(
            prompt=prompt_for_llm,
            model=enhancement_model, # llm_querier should handle default if None
            context="", # No RAG context for query rewriting itself
            conversation_history=None, # Or pass selectively if llm_querier uses it for this task
            user_id=None # Assuming not needed for this internal system call
        )

        # 3. Process the LLM's response.
        # The LLM querier may return either a string or a dict (with 'response' key).
        # Handle both cases for robustness.
        if isinstance(enhanced_query_llm_response, dict):
            enhanced_query_str = enhanced_query_llm_response.get('response', '')
        else:
            enhanced_query_str = enhanced_query_llm_response
        if enhanced_query_str and isinstance(enhanced_query_str, str) and enhanced_query_str.strip():
            enhanced_query = enhanced_query_str.strip()
            # Optional: Add checks to ensure the enhanced query is not worse
            # (e.g., not empty, not excessively long, retains original intent - harder to check)
            if enhanced_query.lower() != original_query.lower():
                logger.info(
                    f"Query enhanced by LLM for RAG: '{original_query}' -> '{enhanced_query}'"
                )
                return enhanced_query
            else:
                logger.info(
                    "LLM returned the same query or a non-substantive change. Using original for RAG."
                )
                return original_query
        else:
            logger.warning(
                "LLM enhancement returned an empty or invalid response. "
                "Falling back to original query."
            )
            return original_query

    except Exception as e:
        logger.error(
            f"Error during LLM-based query enhancement: {str(e)}",
            exc_info=True,
        )
        # Fallback to original query in case of any error
        return original_query

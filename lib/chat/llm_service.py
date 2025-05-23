# /usr/local/lib/timebot/lib/chat/llm_service.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import requests
import json
import logging
import streamlit as st
import time
import random
from typing import Optional, List, Dict, Any
from shared.config import config
# Use config["OLLAMA_API_URL"], config["OLLAMA_MODEL"], etc. directly below.

logger = logging.getLogger(__name__)

# Import external LLM service if enabled
if config["USE_EXTERNAL_LLM"]:
    from chat.external_llm_service import ExternalLLMService
    external_llm_service = None  # Will be initialized in main.py


def initialize_external_llm_service(config, auth_service=None):
    """Initialize the external LLM service with config and auth service"""
    global external_llm_service
    if config["USE_EXTERNAL_LLM"]:
        external_llm_service = ExternalLLMService(config, auth_service)
        logger.debug("External LLM service initialized")


def query_llm(
    prompt: str,
    model: Optional[str] = None,
    context: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main entry point for LLM queries. Routes to external LLM or local Ollama.

    Args:
        prompt: The current user query or enhanced prompt
        model: The specific LLM model to use.
        context: Additional context from RAG
        conversation_history: List of previous messages in the conversation
        user_id: The user ID for rate limiting

    Returns:
        Dictionary with response data and status
    """
    logger.info(f"LLM QUERY - user_id={user_id} prompt=\"{prompt}\"")
    if config["USE_EXTERNAL_LLM"]:
        return query_external_llm_with_retries(
            prompt, model, context, conversation_history, user_id
        )
    else:
        return query_local_ollama(prompt, model, context, conversation_history, user_id)


def query_external_llm_with_retries(
    prompt: str,
    model: Optional[str] = None, 
    context: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query external LLM with retry logic using exponential backoff

    Args:
        prompt: The current user query or enhanced prompt
        model: The specific external LLM model to use.
        context: Additional context from RAG
        conversation_history: List of previous messages in the conversation
        user_id: The user ID for rate limiting

    Returns:
        Dictionary with response data and status
    """
    # Log the start of an external LLM query (INFO)
    logger.info(f"LLM EXTERNAL QUERY - user_id={user_id} model={model} prompt=\"{prompt}\"")
    max_retries = config["EXTERNAL_LLM_API_MAX_RETRIES"]
    base_delay = config["EXTERNAL_LLM_API_RETRY_DELAY"]

    for attempt in range(max_retries + 1):  # +1 for the initial attempt
        try:
            # Call the external LLM service (inline the old query_external_llm logic here)
            # This is the Gemini/Google AI API call
            url = config["EXTERNAL_LLM_API_URL"]
            api_key = config["EXTERNAL_LLM_API_KEY"]
            model_to_use = model if model else config["EXTERNAL_LLM_MODEL"]

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            # Format the conversation history for Gemini API
            contents = []
            if conversation_history:
                for msg in conversation_history:
                    contents.append({
                        "role": msg["role"],
                        "parts": [{"text": msg["content"]}]
                    })
            contents.append({"role": "user", "parts": [{"text": prompt}]})

            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": config["MAX_OUTPUT_TOKENS"],
                    "topP": 0.95,
                    "topK": 40,
                },
            }

            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                error_msg = f"LLM API returned error {response.status_code}: {response.text}"
                logger.error(error_msg)
                result = {"success": False, "error": error_msg, "response": None}
            else:
                result = response.json()
                try:
                    response_text = result["candidates"][0]["content"]["parts"][0]["text"]
                    result = {"success": True, "response": response_text}
                except (KeyError, IndexError) as e:
                    error_msg = f"Error extracting response: {str(e)}"
                    logger.error(error_msg)
                    result = {"success": False, "error": error_msg, "response": None}
            # If successful, return the result
            if result.get("success", False):
                if attempt > 0:
                    logger.info(
                        f"GOOGLE AI - Successful response after {attempt} retries"
                    )
                return result
            # If we got a response but it indicates a permanent error
            if not is_retryable_error(result.get("error", "")):
                logger.warning(
                    f"GOOGLE AI - Non-retryable error: {result.get('error', '')}"
                )
                return result
            logger.warning(
                f"GOOGLE AI - Retryable error on attempt "
                f"{attempt+1}/{max_retries+1}: {result.get('error', '')}"
            )
        except Exception as e:
            logger.error(
                f"GOOGLE AI - Exception on attempt "
                f"{attempt+1}/{max_retries+1}: {str(e)}"
            )
            result = {
                "success": False,
                "error": f"Error communicating with Google AI API: {str(e)}",
                "response": None,
            }
        if attempt == max_retries:
            logger.error(f"GOOGLE AI - All {max_retries+1} attempts failed")
            return result
        delay = base_delay * (2**attempt) + random.uniform(0, 1)
        logger.debug(
            f"GOOGLE AI - Retrying in {delay:.2f} seconds "
            f"(attempt {attempt+1}/{max_retries})"
        )
        time.sleep(delay)
    return result


def is_retryable_error(error_message: str) -> bool:
    """
    Determine if an error should be retried based on the error message

    Args:
        error_message: The error message string

    Returns:
        True if the error is retryable, False otherwise
    """
    # List of error substrings that indicate retryable errors
    retryable_errors = [
        "timeout",
        "connection",
        "network",
        "503",
        "500",
        "429",  # Rate limiting
        "temporarily unavailable",
        "server error",
        "try again",
    ]

    # Check if any retryable error substring is in the error message
    error_lower = error_message.lower()
    return any(err in error_lower for err in retryable_errors)


from .ollama_llm_service import query_local_ollama  # Ollama-specific logic moved here


def query_external_llm(
    prompt: str,
    model: Optional[str] = None, # MODIFIED: Added model parameter
    context: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """
    Send a prompt to external LLM and return the response.

    Args:
        prompt: The current user query or enhanced prompt
        model: The specific external model to use. If None, defaults to EXTERNAL_LLM_MODEL.
        context: Additional context from RAG
        conversation_history: List of previous messages in the conversation
    """
    try:
        model_to_use = model if model else EXTERNAL_LLM_MODEL
        logger.info(
            f"LLM REQUEST - Query LLM API with model: {model_to_use}"
        )

        # For Gemini API, the API key is passed as a query parameter
        # IMPORTANT: If 'model_to_use' needs to change the API endpoint URL itself
        # (e.g. for different Gemini models like gemini-pro vs gemini-flash),
        # the 'url' construction below would need to be made dynamic based on 'model_to_use'.
        # Currently, EXTERNAL_LLM_API_URL is assumed to be the full path to the generateContent
        # endpoint for the default model.
        url = f"{EXTERNAL_LLM_API_URL}?key={EXTERNAL_LLM_API_KEY}"

        # Check if API key is set
        if not config["EXTERNAL_LLM_API_KEY"]:
            error_msg = ("LLM API key is not set. Please set the "
                         "API key in your configuration.")
            logger.error(error_msg)
            st.error(error_msg)
            return None

        headers = {"Content-Type": "application/json"}

        # Build the contents array for LLM API
        contents = []

        # If we have conversation history, format it for Gemini
        if (
            conversation_history and len(conversation_history) > 1
        ):  # More than just the current message
            # Add previous messages (excluding the current one
            # which is the last in the list)
            for msg in conversation_history[:-1]:
                gemini_role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    {"role": gemini_role, "parts": [{"text": msg["content"]}]}
                )

        # Add the current prompt as the final message
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        # Log the formatted messages being sent to LLM
        logger.debug(f"LLM REQUEST - Sending {len(contents)} messages to LLM model: {model_to_use}")
        for i, msg in enumerate(contents):
            # Truncate long messages for logging
            content_preview = (
                msg["parts"][0]["text"][:150] + "..."
                if len(msg["parts"][0]["text"]) > 150
                else msg["parts"][0]["text"]
            )
            logger.debug(
                f"LLM REQUEST - Message {i+1}: {msg['role']} - {content_preview}"
            )

        # Gemini API payload format
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": config["MAX_OUTPUT_TOKENS"],
                "topP": 0.95,
                "topK": 40,
            },
        }

        # Log payload structure (without full message content)
        payload_log = payload.copy()
        payload_log["contents"] = f"[{len(contents)} messages]"
        logger.debug(f"LLM REQUEST - Payload structure: {json.dumps(payload_log)}")

        # Make the API request
        logger.debug(f"LLM REQUEST - Sending request to Gemini API URL: {url}")
        response = requests.post(url, headers=headers, json=payload)

        # Log response status
        logger.debug(
            f"LLM RESPONSE - Received response with status code: "
            f"{response.status_code}"
        )

        # If there's an HTTP error, log the response content
        if response.status_code != 200:
            logger.error(
                f"LLM ERROR - HTTP Error {response.status_code}: {response.text}"
            )
            error_msg = (
                f"LLM API returned error {response.status_code}: {response.text}"
            )
            st.error(error_msg)
            return None

        response.raise_for_status()

        # Parse the JSON response
        logger.debug("LLM RESPONSE - Parsing JSON response...")
        result = response.json()

        # Extract the response text from Gemini's response format
        try:
            response_text = result["candidates"][0]["content"]["parts"][0]["text"]
            logger.debug(
                f"LLM RESPONSE - Successfully extracted response text "
                f"(length: {len(response_text)} chars)"
            )
            logger.debug(f"LLM RESPONSE - Preview: {response_text[:150]}...")
            return response_text
        except (KeyError, IndexError) as e:
            logger.error(f"LLM ERROR - Failed to extract response text: {e}")
            logger.error(
                f"LLM ERROR - Response structure: {json.dumps(result, indent=2)}"
            )
            return "Error: Unexpected response format from Gemini API"

    except requests.exceptions.RequestException as e:
        error_msg = f"Error communicating with Gemini API: {str(e)}"
        logger.error(f"LLM ERROR - {error_msg}")
        # Log more details about the request exception
        if hasattr(e, "response") and e.response is not None:
            logger.error(
                f"LLM ERROR - Response status code: {e.response.status_code}"
            )
            logger.error(f"LLM ERROR - Response content: {e.response.text}")
        st.error(error_msg)
        return None
    except json.JSONDecodeError as e:
        error_msg = f"Error parsing LLM API response as JSON: {str(e)}"
        logger.error(f"LLM ERROR - {error_msg}")
        # Try to log the raw response
        try:
            if "response" in locals():
                logger.error(f"LLM ERROR - Raw response: {response.text}")
        except Exception as e_resp: # Renamed to avoid conflict with outer 'e'
            logger.error(f"LLM ERROR - couldn't get response: {str(e_resp)}")
        st.error(error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error when calling LLM API: {str(e)}"
        logger.error(f"LLM ERROR - {error_msg}")
        logger.exception("LLM ERROR - Full exception details:")
        st.error(error_msg)
        return None



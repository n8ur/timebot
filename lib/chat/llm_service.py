# /usr/local/lib/timebot/lib/chat/llm_service.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# llm_service.py
import requests
import json
import logging
import streamlit as st
import time
import random
from typing import Optional, List, Dict, Any
from chat.chat_config import (
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    EXTERNAL_LLM_ENABLED,
    EXTERNAL_LLM_API_URL,
    EXTERNAL_LLM_API_KEY,
    EXTERNAL_LLM_MODEL,
    MAX_OUTPUT_TOKENS,
    USE_EXTERNAL_LLM,
    ENABLE_OLLAMA_FALLBACK,
    EXTERNAL_LLM_API_MAX_RETRIES,
    EXTERNAL_LLM_API_RETRY_DELAY,
)

logger = logging.getLogger(__name__)

# Import external LLM service if enabled
if USE_EXTERNAL_LLM:
    from chat.external_llm_service import ExternalLLMService
    external_llm_service = None  # Will be initialized in main.py


def initialize_external_llm_service(config, auth_service=None):
    """Initialize the external LLM service with config and auth service"""
    global external_llm_service
    if USE_EXTERNAL_LLM:
        external_llm_service = ExternalLLMService(config, auth_service)
        logger.debug("External LLM service initialized")


def query_llm(
    prompt: str,
    model: Optional[str] = None, 
    context: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
) -> Optional[str]:
    """
    Send a prompt to the LLM API and return the response.
    Automatically routes to either local Ollama, external API,
    or external LLM based on configuration.

    Args:
        prompt: The current user query or enhanced prompt
        model: The model to use. If None, defaults will apply per service.
        context: Additional context from RAG
        conversation_history: List of previous messages in the conversation
        user_id: The user ID for rate limiting (only used with external LLM)
    """
    # Log the prompt and context being sent to the LLM
    logger.debug(f"LLM REQUEST - Prompt: {prompt[:200]}...")
    if context:
        logger.debug(
            f"LLM CONTEXT - RAG context provided (length: {len(context)} chars)"
        )
        # Log the first 500 characters of the context
        logger.debug(f"LLM CONTEXT - RAG context preview: {context[:500]}...")
    else:
        logger.debug("LLM CONTEXT - No RAG context provided")

    # Log conversation history summary
    if conversation_history:
        logger.debug(
            f"LLM CONTEXT - Conversation history: "
            f"{len(conversation_history)} messages"
        )
        for i, msg in enumerate(conversation_history):
            # Truncate long messages for logging
            content_preview = (
                msg["content"][:100] + "..."
                if len(msg["content"]) > 100
                else msg["content"]
            )
            logger.debug(
                f"LLM CONTEXT - Message {i+1}: {msg['role']} - {content_preview}"
            )
    else:
        logger.debug("LLM CONTEXT - No conversation history provided")

    # Route to the appropriate LLM service
    if USE_EXTERNAL_LLM and external_llm_service:
        # Use external LLM service with retries and rate limiting
        result = query_external_llm_with_retries(
            prompt,
            model=model, 
            context=context,
            conversation_history=conversation_history,
            user_id=user_id
        )

        # Store usage information in session state for UI display
        if user_id and result.get("limits") and result.get("usage"):
            st.session_state.ai_limits = result.get("limits", {})
            st.session_state.ai_usage = result.get("usage", {})

        # Handle fallback case
        if result.get("used_fallback", False):
            # Add a note about using fallback
            fallback_note = (
                f"\n\n---\n*Note: This response was generated "
                f"using a fallback model because "
                f"{result.get('fallback_reason', 'you exceeded your quota')}*")
            response = result.get("response", "")
            if response:
                return response + fallback_note
            else:
                return None

        # Return the response or None if there was an error
        if result.get("success", False):
            return result.get("response")
        else:
            error_msg = result.get("error", "Unknown error")
            st.error(error_msg)
            return None
    elif EXTERNAL_LLM_ENABLED:
        return query_external_llm(
            prompt,
            model=model, 
            context=context,
            conversation_history=conversation_history
        )
    else:
        # MODIFIED: Use OLLAMA_MODEL as default if no model is specified for local Ollama
        ollama_model_to_use = model if model else OLLAMA_MODEL
        return query_local_ollama(
            prompt,
            model=ollama_model_to_use,
            context=context,
            conversation_history=conversation_history
        )


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
    max_retries = EXTERNAL_LLM_API_MAX_RETRIES
    base_delay = EXTERNAL_LLM_API_RETRY_DELAY

    for attempt in range(max_retries + 1):  # +1 for the initial attempt
        try:
            # Call the external LLM service
            # MODIFIED: Pass model to external_llm_service.query_external_llm(
            # This assumes external_llm_service.query_external_llm( can handle the 'model' arg.
            result = external_llm_service.query_external_llm(
                prompt,
                model=model, 
                context=context,
                conversation_history=conversation_history,
                user_id=user_id
            )

            # If successful, return the result
            if result.get("success", False):
                if attempt > 0:
                    logger.info(
                        f"GOOGLE AI - Successful response after {attempt} retries"
                    )
                return result

            # If we got a response but it indicates a permanent error
            # (not a connectivity issue)
            # don't retry and just return the error
            if not is_retryable_error(result.get("error", "")):
                logger.warning(
                    f"GOOGLE AI - Non-retryable error: {result.get('error', '')}"
                )
                return result

            # Log the error for retryable errors
            logger.warning(
                f"GOOGLE AI - Retryable error on attempt "
                f"{attempt+1}/{max_retries+1}: {result.get('error', '')}"
            )

        except Exception as e:
            # Log any unexpected exceptions
            logger.error(
                f"GOOGLE AI - Exception on attempt "
                f"{attempt+1}/{max_retries+1}: {str(e)}"
            )

            # Create an error result to return if all retries fail
            result = {
                "success": False,
                "error": f"Error communicating with Google AI API: {str(e)}",
                "response": None,
            }

        # If this was the last attempt, return the error result
        if attempt == max_retries:
            logger.error(f"GOOGLE AI - All {max_retries+1} attempts failed")
            return result

        # Calculate delay with exponential backoff and jitter
        delay = base_delay * (2**attempt) + random.uniform(0, 1)
        logger.info(
            f"GOOGLE AI - Retrying in {delay:.2f} seconds "
            f"(attempt {attempt+1}/{max_retries})"
        )
        time.sleep(delay)

    # This should never be reached due to the return in the loop
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


def query_local_ollama(
    prompt: str,
    model: str = OLLAMA_MODEL, # Signature unchanged, query_llm ensures a valid model is passed
    context: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """
    Send a prompt to the local Ollama API and return the response.

    Args:
        prompt: The current user query or enhanced prompt
        model: The model to use
        context: Additional context from RAG
        conversation_history: List of previous messages in the conversation
    """
    try:
        # For Ollama, we'll use the system prompt with context and
        # include conversation history
        # Note: We're using the enhanced prompt directly since it
        # already includes the system instructions and context

        # Format the conversation history for Ollama if available
        messages = []

        # If we have conversation history, format it for Ollama
        if (
            conversation_history and len(conversation_history) > 1
        ):  # More than just the current message
            # Add previous messages (excluding the current
            # one which is the last in the list)
            for msg in conversation_history[:-1]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Add the current prompt as the final message
        messages.append({"role": "user", "content": prompt})

        # Prepare the payload
        payload = {"model": model, "messages": messages, "stream": False}

        # Log the formatted messages being sent to Ollama
        # MODIFIED: Include model name in log
        logger.info(f"OLLAMA REQUEST - Sending {len(messages)} messages to Ollama model: {model}")
        for i, msg in enumerate(messages):
            # Truncate long messages for logging
            content_preview = (
                msg["content"][:150] + "..."
                if len(msg["content"]) > 150
                else msg["content"]
            )
            logger.debug(
                f"OLLAMA REQUEST - Message {i+1}: {msg['role']} - {content_preview}"
            )

        # Log the full payload structure (without full message content)
        payload_log = payload.copy()
        payload_log["messages"] = f"[{len(messages)} messages]"
        logger.debug(f"OLLAMA REQUEST - Payload structure: {json.dumps(payload_log)}")

        # Make the API request
        response = requests.post(f"{OLLAMA_API_URL}/chat/completions", json=payload)
        response.raise_for_status()

        result = response.json()

        # Log a summary of the response
        if "choices" in result and len(result["choices"]) > 0:
            response_text = result["choices"][0]["message"]["content"]
            logger.info(
                f"OLLAMA RESPONSE - Received response "
                f"(length: {len(response_text)} chars)"
            )
            logger.debug(f"OLLAMA RESPONSE - Preview: {response_text[:150]}...")
            return response_text
        else:
            # Fallback to the old API format if needed
            response_text = result.get("response", "")
            logger.info(
                f"OLLAMA RESPONSE - Received response using "
                f"old format (length: {len(response_text)} chars)"
            )
            logger.debug(f"OLLAMA RESPONSE - Preview: {response_text[:150]}...")
            return response_text

    except requests.exceptions.RequestException as e:
        error_msg = f"Error communicating with Ollama: {str(e)}"
        logger.error(error_msg)

        # Only try fallback if explicitly enabled
        if ENABLE_OLLAMA_FALLBACK:
            try:
                logger.info(
                    "OLLAMA FALLBACK - Attempting fallback to older Ollama API format"
                )
                # Format the conversation history as a single text prompt
                conversation_text = ""
                if conversation_history and len(conversation_history) > 1:
                    for msg in conversation_history[:-1]:
                        role_prefix = (
                            "User: " if msg["role"] == "user" else "Assistant: "
                        )
                        conversation_text += f"{role_prefix}{msg['content']}\n\n"

                # Add the current prompt
                full_prompt = f"{conversation_text}User: {prompt}\n\nAssistant: "

                # Log the fallback prompt
                logger.info(
                    f"OLLAMA FALLBACK - Using fallback prompt "
                    f"(length: {len(full_prompt)} chars)"
                )
                logger.debug(
                    f"OLLAMA FALLBACK - Prompt preview: {full_prompt[:200]}..."
                )

                # Make the API request with the older format
                payload = {"model": model, "prompt": full_prompt, "stream": False}

                response = requests.post(OLLAMA_API_URL, json=payload)
                response.raise_for_status()

                result = response.json()
                response_text = result.get("response", "")

                logger.info(
                    f"OLLAMA FALLBACK - Received fallback response "
                    f"(length: {len(response_text)} chars)"
                )
                logger.debug(f"OLLAMA FALLBACK - Preview: {response_text[:150]}...")

                return response_text

            except Exception as fallback_error:
                logger.error(
                    f"OLLAMA FALLBACK - Fallback also failed: {str(fallback_error)}"
                )
                st.error(error_msg)
                return None
        else:
            logger.info(
                "OLLAMA FALLBACK - Fallback is disabled, not "
                "attempting older API format"
            )
            st.error(error_msg)
            return None

    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Error parsing Ollama response: {str(e)}"
        logger.error(error_msg)
        st.error(error_msg)
        return None


def query_external_llm(
    prompt: str,
    model: Optional[str] = None, # MODIFIED: Added model parameter
    context: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """
    Send a prompt to Google Gemini API and return the response.

    Args:
        prompt: The current user query or enhanced prompt
        model: The specific external model to use. If None, defaults to EXTERNAL_LLM_MODEL.
        context: Additional context from RAG
        conversation_history: List of previous messages in the conversation
    """
    try:
        # MODIFIED: Use provided model or default to EXTERNAL_LLM_MODEL
        model_to_use = model if model else EXTERNAL_LLM_MODEL
        logger.info(
            f"GEMINI REQUEST - Query Gemini API with model: {model_to_use}"
        )

        # For Gemini API, the API key is passed as a query parameter
        # IMPORTANT: If 'model_to_use' needs to change the API endpoint URL itself
        # (e.g. for different Gemini models like gemini-pro vs gemini-flash),
        # the 'url' construction below would need to be made dynamic based on 'model_to_use'.
        # Currently, EXTERNAL_LLM_API_URL is assumed to be the full path to the generateContent
        # endpoint for the default model.
        url = f"{EXTERNAL_LLM_API_URL}?key={EXTERNAL_LLM_API_KEY}"

        # Check if API key is set
        if not EXTERNAL_LLM_API_KEY:
            error_msg = ("Gemini API key is not set. Please set the "
                         "API key in your configuration.")
            logger.error(error_msg)
            st.error(error_msg)
            return None

        headers = {"Content-Type": "application/json"}

        # Build the contents array for Gemini API
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

        # Log the formatted messages being sent to Gemini
        # MODIFIED: Include model_to_use in log
        logger.debug(f"GEMINI REQUEST - Sending {len(contents)} messages to Gemini model: {model_to_use}")
        for i, msg in enumerate(contents):
            # Truncate long messages for logging
            content_preview = (
                msg["parts"][0]["text"][:150] + "..."
                if len(msg["parts"][0]["text"]) > 150
                else msg["parts"][0]["text"]
            )
            logger.debug(
                f"GEMINI REQUEST - Message {i+1}: {msg['role']} - {content_preview}"
            )

        # Gemini API payload format
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "topP": 0.95,
                "topK": 40,
            },
        }

        # Log payload structure (without full message content)
        payload_log = payload.copy()
        payload_log["contents"] = f"[{len(contents)} messages]"
        logger.debug(f"GEMINI REQUEST - Payload structure: {json.dumps(payload_log)}")

        # Make the API request
        # MODIFIED: Log the URL being used
        logger.info(f"GEMINI REQUEST - Sending request to Gemini API URL: {url}")
        response = requests.post(url, headers=headers, json=payload)

        # Log response status
        logger.info(
            f"GEMINI RESPONSE - Received response with status code: "
            f"{response.status_code}"
        )

        # If there's an HTTP error, log the response content
        if response.status_code != 200:
            logger.error(
                f"GEMINI ERROR - HTTP Error {response.status_code}: {response.text}"
            )
            error_msg = (
                f"Gemini API returned error {response.status_code}: {response.text}"
            )
            st.error(error_msg)
            return None

        response.raise_for_status()

        # Parse the JSON response
        logger.debug("GEMINI RESPONSE - Parsing JSON response...")
        result = response.json()

        # Extract the response text from Gemini's response format
        try:
            response_text = result["candidates"][0]["content"]["parts"][0]["text"]
            logger.info(
                f"GEMINI RESPONSE - Successfully extracted response text "
                f"(length: {len(response_text)} chars)"
            )
            logger.debug(f"GEMINI RESPONSE - Preview: {response_text[:150]}...")
            return response_text
        except (KeyError, IndexError) as e:
            logger.error(f"GEMINI ERROR - Failed to extract response text: {e}")
            logger.error(
                f"GEMINI ERROR - Response structure: {json.dumps(result, indent=2)}"
            )
            return "Error: Unexpected response format from Gemini API"

    except requests.exceptions.RequestException as e:
        error_msg = f"Error communicating with Gemini API: {str(e)}"
        logger.error(f"GEMINI ERROR - {error_msg}")
        # Log more details about the request exception
        if hasattr(e, "response") and e.response is not None:
            logger.error(
                f"GEMINI ERROR - Response status code: {e.response.status_code}"
            )
            logger.error(f"GEMINI ERROR - Response content: {e.response.text}")
        st.error(error_msg)
        return None
    except json.JSONDecodeError as e:
        error_msg = f"Error parsing Gemini API response as JSON: {str(e)}"
        logger.error(f"GEMINI ERROR - {error_msg}")
        # Try to log the raw response
        try:
            if "response" in locals():
                logger.error(f"GEMINI ERROR - Raw response: {response.text}")
        except Exception as e_resp: # Renamed to avoid conflict with outer 'e'
            logger.error(f"GEMINI ERROR - couldn't get response: {str(e_resp)}") # Corrected typo from GEIMINI
        st.error(error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error when calling Gemini API: {str(e)}"
        logger.error(f"GEMINI ERROR - {error_msg}")
        logger.exception("GEMINI ERROR - Full exception details:")
        st.error(error_msg)
        return None



# ollama_llm_service.py
# Contains all Ollama-specific LLM logic, extracted from llm_service.py
import requests
import json
import logging
from typing import Optional, List, Dict, Any
from shared.config import config

logger = logging.getLogger(__name__)

# These should be defined in config or set here for backward compatibility
OLLAMA_API_URL = config.get("OLLAMA_API_URL", "http://localhost:11434/api")
ENABLE_OLLAMA_FALLBACK = config.get("ENABLE_OLLAMA_FALLBACK", False)


def query_local_ollama(
    prompt: str,
    model: str = config["OLLAMA_MODEL"],
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
        messages = []
        if conversation_history and len(conversation_history) > 1:
            for msg in conversation_history[:-1]:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": model, "messages": messages, "stream": False}
        logger.info(f"OLLAMA REQUEST - Sending {len(messages)} messages to Ollama model: {model}")
        for i, msg in enumerate(messages):
            content_preview = (
                msg["content"][:150] + "..." if len(msg["content"]) > 150 else msg["content"]
            )
            logger.debug(f"OLLAMA REQUEST - Message {i+1}: {msg['role']} - {content_preview}")
        payload_log = payload.copy()
        payload_log["messages"] = f"[{len(messages)} messages]"
        logger.debug(f"OLLAMA REQUEST - Payload structure: {json.dumps(payload_log)}")
        response = requests.post(f"{OLLAMA_API_URL}/chat/completions", json=payload)
        response.raise_for_status()
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            response_text = result["choices"][0]["message"]["content"]
            logger.info(f"OLLAMA RESPONSE - Received response (length: {len(response_text)} chars)")
            logger.debug(f"OLLAMA RESPONSE - Preview: {response_text[:150]}...")
            return response_text
        else:
            response_text = result.get("response", "")
            logger.info(f"OLLAMA RESPONSE - Received response using old format (length: {len(response_text)} chars)")
            logger.debug(f"OLLAMA RESPONSE - Preview: {response_text[:150]}...")
            return response_text
    except requests.exceptions.RequestException as e:
        error_msg = f"Error communicating with Ollama: {str(e)}"
        logger.error(error_msg)
        if ENABLE_OLLAMA_FALLBACK:
            try:
                logger.info("OLLAMA FALLBACK - Attempting fallback to older Ollama API format")
                conversation_text = ""
                if conversation_history and len(conversation_history) > 1:
                    for msg in conversation_history[:-1]:
                        role_prefix = ("User: " if msg["role"] == "user" else "Assistant: ")
                        conversation_text += f"{role_prefix}{msg['content']}\n\n"
                full_prompt = f"{conversation_text}User: {prompt}\n\nAssistant: "
                logger.info(f"OLLAMA FALLBACK - Using fallback prompt (length: {len(full_prompt)} chars)")
                logger.debug(f"OLLAMA FALLBACK - Prompt preview: {full_prompt[:200]}...")
                payload = {"model": model, "prompt": full_prompt, "stream": False}
                response = requests.post(OLLAMA_API_URL, json=payload)
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "")
                logger.info(f"OLLAMA FALLBACK - Received fallback response (length: {len(response_text)} chars)")
                logger.debug(f"OLLAMA FALLBACK - Preview: {response_text[:150]}...")
                return response_text
            except Exception as fallback_error:
                logger.error(f"OLLAMA FALLBACK - Fallback also failed: {str(fallback_error)}")
                return None
        else:
            logger.info("OLLAMA FALLBACK - Fallback is disabled, not attempting older API format")
            return None
    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Error parsing Ollama response: {str(e)}"
        logger.error(error_msg)
        return None

# google_ai_service.py
import requests
import json
import time
import datetime
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class GoogleAIService:
    def __init__(self, config, auth_service=None):
        """
        Initialize the Google AI Service with configuration
        and authentication service.

        Args:
            config: Application configuration dictionary
            auth_service: Firebase authentication service instance
        """
        self.config = config
        self.auth_service = auth_service

        # Google AI API configuration
        self.api_key = config.get("EXTERNAL_LLM_API_KEY", "")
        self.api_url = config.get("EXTERNAL_LLM_API_URL", "")
        self.model = config.get("EXTERNAL_LLM_MODEL", "")
        self.max_output_tokens = config.get("MAX_OUTPUT_TOKENS", 2048)

        # Rate limiting configuration
        self.default_daily_limit = config.get("DEFAULT_DAILY_LIMIT", 10)
        self.default_monthly_limit = config.get("DEFAULT_MONTHLY_LIMIT", 100)

        # Fallback configuration
        self.use_fallback = config.get("USE_FALLBACK_ON_LIMIT", True)
        self.fallback_model = config.get("FALLBACK_MODEL", "ollama")

    def check_rate_limits(self, user_id: str) -> Dict[str, Any]:
        """
        Check if the user has exceeded their rate limits.

        Args:
            user_id: The Firebase user ID

        Returns:
            Dict with keys:
                allowed: Boolean indicating if request is allowed
                reason: String reason if not allowed
                limits: Dict containing user's limits
                usage: Dict containing user's current usage
        """
        if not self.auth_service or not user_id:
            # If no auth service or user_id, use default limits
            return {"allowed": True, "limits": {}, "usage": {}}

        try:
            # Get user data from Firebase
            db = self.auth_service.db
            user_doc = db.collection("users").document(user_id).get()
            if not user_doc.exists:
                return {"allowed": True, "limits": {}, "usage": {}}
            user_data = user_doc.to_dict()
            user_role = user_data.get("role", "free")

            # Get user-specific limits or use defaults based on role
            limits = user_data.get("limits", {}).get("google_ai", {})
            daily_limit = limits.get(
                "daily", self._get_default_limit_for_role(user_role, "daily")
            )
            monthly_limit = limits.get(
                "monthly", self._get_default_limit_for_role(user_role, "monthly")
            )

            # Get current usage
            usage = user_data.get("usage", {}).get("google_ai", {})
            daily_usage = usage.get("daily", {})
            monthly_usage = usage.get("monthly", {})

            # Check if reset is needed
            current_time = int(time.time() * 1000)  # Current time in milliseconds

            # Reset daily counter if needed
            daily_count = daily_usage.get("count", 0)
            daily_reset_at = daily_usage.get("reset_at", 0)
            if self._should_reset_counter(daily_reset_at, "daily"):
                daily_count = 0
                daily_reset_at = self._get_next_reset_time("daily")

            # Reset monthly counter if needed
            monthly_count = monthly_usage.get("count", 0)
            monthly_reset_at = monthly_usage.get("reset_at", 0)
            if self._should_reset_counter(monthly_reset_at, "monthly"):
                monthly_count = 0
                monthly_reset_at = self._get_next_reset_time("monthly")

            # Check if user has exceeded limits
            if daily_count >= daily_limit:
                reason_message = (
                    f"Daily limit of {daily_limit} requests exceeded. "
                    f"Resets in {self._format_time_until(daily_reset_at)}."
                )
                return {
                    "allowed": False,
                    "reason": reason_message,
                    "limits": {"daily": daily_limit, "monthly": monthly_limit},
                    "usage": {"daily": daily_count, "monthly": monthly_count},
                }

            if monthly_count >= monthly_limit:
                reason_message = (
                    f"Monthly limit of {monthly_limit} requests exceeded. "
                    f"Resets in {self._format_time_until(monthly_reset_at)}."
                )
                return {
                    "allowed": False,
                    "reason": reason_message,
                    "limits": {"daily": daily_limit, "monthly": monthly_limit},
                    "usage": {"daily": daily_count, "monthly": monthly_count},
                }

            # User is within limits
            return {
                "allowed": True,
                "limits": {"daily": daily_limit, "monthly": monthly_limit},
                "usage": {"daily": daily_count, "monthly": monthly_count},
                "reset": {"daily": daily_reset_at, "monthly": monthly_reset_at},
            }

        except Exception as e:
            logger.error(f"Error checking rate limits: {str(e)}")
            # If there's an error, allow the request but log the error
            return {"allowed": True, "error": str(e)}

    def update_usage_counters(self, user_id: str) -> bool:
        """
        Update the usage counters for a user after a successful API call.

        Args:
            user_id: The Firebase user ID

        Returns:
            Boolean indicating if the update was successful
        """
        if not self.auth_service or not user_id:
            return True

        try:
            # Get user data from Firebase
            db = self.auth_service.db
            user_doc = (
                db.collection("users").document(user_id).get()
            )  # This returns a DocumentSnapshot
            user_data = user_doc.to_dict()  # Convert directly to dictionary

            # Get current usage
            usage = user_data.get("usage", {}).get("google_ai", {})
            daily_usage = usage.get("daily", {})
            monthly_usage = usage.get("monthly", {})

            # Check if reset is needed
            current_time = int(time.time() * 1000)  # Current time in milliseconds

            # Update daily counter
            daily_count = daily_usage.get("count", 0)
            daily_reset_at = daily_usage.get("reset_at", 0)
            if self._should_reset_counter(daily_reset_at, "daily"):
                daily_count = 1
                daily_reset_at = self._get_next_reset_time("daily")
            else:
                daily_count += 1

            # Update monthly counter
            monthly_count = monthly_usage.get("count", 0)
            monthly_reset_at = monthly_usage.get("reset_at", 0)
            if self._should_reset_counter(monthly_reset_at, "monthly"):
                monthly_count = 1
                monthly_reset_at = self._get_next_reset_time("monthly")
            else:
                monthly_count += 1

            # Update total counter
            total_count = usage.get("total", 0) + 1

            # Update the database - need to use document reference, not snapshot
            user_ref = db.collection("users").document(
                user_id
            )  # Get document reference
            user_ref.update(
                {
                    "usage.google_ai.daily.count": daily_count,
                    "usage.google_ai.daily.reset_at": daily_reset_at,
                    "usage.google_ai.monthly.count": monthly_count,
                    "usage.google_ai.monthly.reset_at": monthly_reset_at,
                    "usage.google_ai.total": total_count,
                    "usage.google_ai.last_used_at": current_time,
                }
            )

            logger.debug(
                f"Updated usage counters for user {user_id}: "
                f"daily={daily_count}, monthly={monthly_count}, "
                f"total={total_count}"
            )
            return True

        except Exception as e:
            logger.error(f"Error updating usage counters: {str(e)}")
            return False

    def query_google_ai(
        self,
        prompt: str,
        model: Optional[str] = None,
        context: str = "",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a prompt to Google AI API with rate limiting and usage tracking.

        Args:
            prompt: The current user query or enhanced prompt
            context: Additional context from RAG
            conversation_history: List of previous messages in the conversation
            user_id: The Firebase user ID for rate limiting

        Returns:
            Dict with keys:
                success: Boolean indicating if the request was successful
                response: The response text if successful
                error: Error message if not successful
                used_fallback: Boolean indicating if fallback was used
                limits: Dict containing user's limits
                usage: Dict containing user's current usage
        """
        # Check if API key is set
        if not self.api_key:
            return {
                "success": False,
                "error": (
                    "Google AI API key is not set. Please "
                    "set the API key in your configuration."
                ),
            }

        # Check rate limits if user_id is provided
        if user_id:
            rate_limit_check = self.check_rate_limits(user_id)
            if not rate_limit_check.get("allowed", True):
                # If fallback is enabled, use fallback model
                if self.use_fallback:
                    logger.info(
                        f"User {user_id} exceeded rate limits. Using fallback model."
                    )
                    return self._use_fallback_model(
                        prompt, context, conversation_history, rate_limit_check
                    )
                else:
                    # Otherwise, return error
                    return {
                        "success": False,
                        "error": rate_limit_check.get("reason", "Rate limit exceeded"),
                        "limits": rate_limit_check.get("limits", {}),
                        "usage": rate_limit_check.get("usage", {}),
                    }

        try:
            model_to_use_for_api = model if model else self.model
            final_api_url = self.api_url

            # self.model is the NAME of the default model 
            # (e.g., "gemini-1.5-flash-latest")
            # self.api_url is the FULL URL for the default model 
            # (e.g., "https://.../models/gemini-1.5-flash-latest:generateContent")

            if model and model != self.model:
                if self.model and self.model in self.api_url:
                    final_api_url = self.api_url.replace(self.model, model, 1)
                    logger.info(
                        f"GOOGLE_AI REQUEST - Overriding default model URL. "
                        f"Original URL: {self.api_url}, New URL: {final_api_url} for model '{model}'"
                    )
                elif "{model_name}" in self.api_url: # Check if self.api_url is a template
                    final_api_url = self.api_url.replace("{model_name}", model)
                    logger.info(
                        f"GOOGLE_AI REQUEST - Using template URL. "
                        f"Original URL: {self.api_url}, New URL: {final_api_url} for model '{model}'"
                    )
                else:
                    # Fallback or error: Cannot determine how to form URL for the new model
                    logger.warning(
                        f"GOOGLE_AI REQUEST - Cannot reliably form URL for specific model '{model}' "
                        f"from default URL '{self.api_url}' and default model name '{self.model}'. "
                        f"Using default URL. Ensure EXTERNAL_LLM_API_URL is either a full path to a specific model "
                        f"or a template like 'https://.../models/{{model_name}}:generateContent'."
                    )
    
            # The API key is passed as a query parameter
            url_with_key = f"{final_api_url}?key={self.api_key}"

            # Log the API request attempt
            logger.debug(
                f"GOOGLE_AI REQUEST - Attempting to query Google "
                f"AI API with effective model name: {model_to_use_for_api} at URL {final_api_url}"
            )

            headers = {"Content-Type": "application/json"}

            # Build the contents array for Google AI API
            contents = []

            # If we have conversation history, format it for the API
            if (
                conversation_history and len(conversation_history) > 1
            ):  # More than just the current message
                # Add previous messages (excluding the current one
                # which is the last in the list)
                for msg in conversation_history[:-1]:
                    api_role = "user" if msg["role"] == "user" else "model"
                    contents.append(
                        {"role": api_role, "parts": [{"text": msg["content"]}]}
                    )

            # Add the current prompt as the final message
            contents.append({"role": "user", "parts": [{"text": prompt}]})

            # Log the formatted messages being sent to Google AI
            logger.debug(
                f"GOOGLE_AI REQUEST - Sending {len(contents)} messages to Google AI"
            )
            for i, msg in enumerate(contents):
                # Truncate long messages for logging
                content_preview = (
                    msg["parts"][0]["text"][:150] + "..."
                    if len(msg["parts"][0]["text"]) > 150
                    else msg["parts"][0]["text"]
                )
                logger.debug(
                    f"GOOGLE_AI REQUEST - Message {i+1}: {msg['role']} "
                    f"- {content_preview}"
                )

            # Google AI API payload format
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": self.max_output_tokens,
                    "topP": 0.95,
                    "topK": 40,
                },
            }

            # Log payload structure (without full message content)
            payload_log = payload.copy()
            payload_log["contents"] = f"[{len(contents)} messages]"
            logger.debug(
                f"GOOGLE_AI REQUEST - Payload structure: {json.dumps(payload_log)}"
            )

            # Make the API request
            logger.debug("GOOGLE_AI REQUEST - Sending request to {url_with_key}")
            response = requests.post(url_with_key, headers=headers, json=payload)

            # Log response status
            logger.debug(
                f"GOOGLE_AI RESPONSE - "
                f"Received response with status code: {response.status_code}"
            )

            # If there's an HTTP error, log the response content
            if response.status_code != 200:
                logger.error(
                    f"GOOGLE_AI ERROR - "
                    f"HTTP Error {response.status_code}: {response.text}"
                )
                return {
                    "success": False,
                    "error": f"Google AI API returned error "
                    f"{response.status_code}: {response.text}",
                }

            # Parse the JSON response
            logger.debug("GOOGLE_AI RESPONSE - Parsing JSON response...")
            result = response.json()

            # Extract the response text from Google AI's response format
            try:
                response_text = result["candidates"][0]["content"]["parts"][0]["text"]
                logger.debug(
                    f"GOOGLE_AI RESPONSE - "
                    f"Successfully extracted response text "
                    f"(length: {len(response_text)} chars)"
                )
                logger.debug(
                    f"GOOGLE_AI RESPONSE - Preview: " f"{response_text[:150]}..."
                )

                # Update usage counters if user_id is provided
                if user_id:
                    self.update_usage_counters(user_id)

                # Return successful response with rate limit info if available
                if user_id:
                    rate_limit_info = self.check_rate_limits(user_id)
                    return {
                        "success": True,
                        "response": response_text,
                        "limits": rate_limit_info.get("limits", {}),
                        "usage": rate_limit_info.get("usage", {}),
                    }
                else:
                    return {"success": True, "response": response_text}

            except (KeyError, IndexError) as e:
                logger.error(f"GOOGLE_AI ERROR - Failed to extract response text: {e}")
                logger.error(
                    f"GOOGLE_AI ERROR - Response structure: "
                    f"{json.dumps(result, indent=2)}"
                )
                return {
                    "success": False,
                    "error": "Error: Unexpected response format from Google AI API",
                }

        except requests.exceptions.RequestException as e:
            error_msg = f"Error communicating with Google AI API: {str(e)}"
            logger.error(f"GOOGLE_AI ERROR - {error_msg}")
            # Log more details about the request exception
            if hasattr(e, "response") and e.response is not None:
                logger.error(
                    f"GOOGLE_AI ERROR - Response status code: {e.response.status_code}"
                )
                logger.error(f"GOOGLE_AI ERROR - Response content: {e.response.text}")
            return {"success": False, "error": error_msg}
        except json.JSONDecodeError as e:
            error_msg = f"Error parsing Google AI API response as JSON: {str(e)}"
            logger.error(f"GOOGLE_AI ERROR - {error_msg}")
            # Try to log the raw response
            try:
                if "response" in locals():
                    logger.error(f"GOOGLE_AI ERROR - Raw response: {response.text}")
            except Exception as e:
                logger.error(f"Failed to log raw GOOGLE_AI response: {e}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error when calling Google AI API: {str(e)}"
            logger.error(f"GOOGLE_AI ERROR - {error_msg}")
            logger.exception("GOOGLE_AI ERROR - Full exception details:")
            return {"success": False, "error": error_msg}

    def _use_fallback_model(
        self,
        prompt: str,
        context: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        rate_limit_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Use fallback model when rate limits are exceeded.

        Args:
            prompt: The current user query or enhanced prompt
            context: Additional context from RAG
            conversation_history: List of previous messages in the conversation
            rate_limit_info: Rate limit information

        Returns:
            Dict with response information
        """
        # Check if Ollama fallback is enabled
        if not self.use_fallback or self.fallback_model != "ollama":
            # Return a clear error message about quota exceeded without using fallback
            return {
                "success": False,
                "error": rate_limit_info.get(
                    "reason",
                    "You have exceeded your API quota. Please try again later.",
                ),
                "limits": rate_limit_info.get("limits", {}),
                "usage": rate_limit_info.get("usage", {}),
            }

        # If we get here, Ollama fallback is enabled
        from chat.llm_service import query_local_ollama

        try:
            # Log fallback usage
            logger.info(
                f"FALLBACK - Using fallback model {self.fallback_model} "
                f"due to rate limits"
            )

            # Call the local Ollama model
            response_text = query_local_ollama(
                prompt, self.fallback_model, context, conversation_history
            )

            if response_text:
                return {
                    "success": True,
                    "response": response_text,
                    "used_fallback": True,
                    "fallback_reason": rate_limit_info.get(
                        "reason", "Rate limit exceeded"
                    ),
                    "limits": rate_limit_info.get("limits", {}),
                    "usage": rate_limit_info.get("usage", {}),
                }
            else:
                return {
                    "success": False,
                    "error": (
                        "You have exceeded your API quota, and "
                        "the fallback model failed to generate a response."
                    ),
                    "used_fallback": True,
                    "limits": rate_limit_info.get("limits", {}),
                    "usage": rate_limit_info.get("usage", {}),
                }
        except Exception as e:
            logger.error(f"FALLBACK ERROR - Error using fallback model: {str(e)}")
            return {
                "success": False,
                "error": (
                    f"You have exceeded your API quota, and the "
                    f"fallback model encountered an error: {str(e)}"
                ),
                "used_fallback": True,
                "limits": rate_limit_info.get("limits", {}),
                "usage": rate_limit_info.get("usage", {}),
            }

    def _get_default_limit_for_role(self, role: str, limit_type: str) -> int:
        """Get the default limit for a user role"""
        role_limits = {
            "free": {
                "daily": self.config.get("FREE_DAILY_LIMIT", 5),
                "monthly": self.config.get("FREE_MONTHLY_LIMIT", 50),
            },
            "premium": {
                "daily": self.config.get("PREMIUM_DAILY_LIMIT", 50),
                "monthly": self.config.get("PREMIUM_MONTHLY_LIMIT", 500),
            },
            "admin": {
                "daily": self.config.get("ADMIN_DAILY_LIMIT", 1000),
                "monthly": self.config.get("ADMIN_MONTHLY_LIMIT", 10000),
            },
        }

        return role_limits.get(role, role_limits["free"]).get(
            limit_type, self.default_daily_limit
        )

    def _should_reset_counter(self, reset_timestamp: int, counter_type: str) -> bool:
        """Check if a counter should be reset based on its reset timestamp"""
        if not reset_timestamp:
            return True

        current_time = int(time.time() * 1000)  # Current time in milliseconds
        return current_time >= reset_timestamp

    def _get_next_reset_time(self, counter_type: str) -> int:
        """Get the next reset time for a counter type"""
        now = datetime.datetime.now()

        if counter_type == "daily":
            # Reset at midnight
            tomorrow = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + datetime.timedelta(days=1)
            return int(tomorrow.timestamp() * 1000)
        elif counter_type == "monthly":
            # Reset on the 1st of next month
            if now.month == 12:
                next_month = now.replace(
                    year=now.year + 1,
                    month=1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                next_month = now.replace(
                    month=now.month + 1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            return int(next_month.timestamp() * 1000)
        else:
            # Default to 24 hours from now
            return int((now + datetime.timedelta(days=1)).timestamp() * 1000)

    def _format_time_until(self, timestamp_ms: int) -> str:
        """Format the time until a timestamp in a human-readable format"""
        if not timestamp_ms:
            return "unknown time"

        now = datetime.datetime.now()
        reset_time = datetime.datetime.fromtimestamp(timestamp_ms / 1000)
        delta = reset_time - now

        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if days > 0:
            return f"{days} days, {hours} hours"
        elif hours > 0:
            return f"{hours} hours, {minutes} minutes"
        else:
            return f"{minutes} minutes, {seconds} seconds"

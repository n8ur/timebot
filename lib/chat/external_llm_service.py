# /usr/local/lib/timebot/lib/chat/external_llm_service.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# external_llm_service.py
import requests
import json
import time
import datetime
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class ExternalLLMService:
    def __init__(self, config, auth_service=None):
        """
        Initialize the External LLM Service with configuration
        and authentication service.

        Args:
            config: Application configuration dictionary
            auth_service: Firebase authentication service instance
        """
        self.config = config
        self.auth_service = auth_service

        # External LLM API configuration
        self.api_key = config["EXTERNAL_LLM_API_KEY"]
        self.api_url = config["EXTERNAL_LLM_API_URL"]
        self.model = config["EXTERNAL_LLM_MODEL"]
        self.max_output_tokens = config["MAX_OUTPUT_TOKENS"]

        # Debug log for credential loading
        if self.api_key:
            obfuscated_key = self.api_key[:6] + "..." + self.api_key[-4:]
        else:
            obfuscated_key = "<EMPTY>"
        logger.info(f"[DEBUG] ExternalLLMService initialized with API URL: {self.api_url}, API KEY: {obfuscated_key}")

        # Rate limiting configuration
        self.default_daily_limit = config["FREE_DAILY_LIMIT"]
        self.default_monthly_limit = config["FREE_MONTHLY_LIMIT"]

        # Fallback configuration
        self.use_fallback = config["USE_FALLBACK_ON_LIMIT"]
        self.fallback_model = config["FALLBACK_MODEL"]

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
            limits = user_data.get("limits", {}).get("external_llm", {})
            daily_limit = limits.get(
                "daily", self._get_default_limit_for_role(user_role, "daily")
            )
            monthly_limit = limits.get(
                "monthly", self._get_default_limit_for_role(user_role, "monthly")
            )

            # Get current usage
            usage = user_data.get("usage", {}).get("external_llm", {})
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

            return {
                "allowed": True,
                "limits": {"daily": daily_limit, "monthly": monthly_limit},
                "usage": {"daily": daily_count, "monthly": monthly_count},
            }
        except Exception as e:
            logger.error(f"RATE LIMIT ERROR - {str(e)}")
            return {"allowed": True, "limits": {}, "usage": {}}

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
            db = self.auth_service.db
            user_ref = db.collection("users").document(user_id)
            user_doc = user_ref.get()
            if not user_doc.exists:
                return True
            user_data = user_doc.to_dict()
            usage = user_data.get("usage", {}).get("external_llm", {})
            daily_usage = usage.get("daily", {})
            monthly_usage = usage.get("monthly", {})
            current_time = int(time.time() * 1000)

            # Update daily usage
            daily_count = daily_usage.get("count", 0) + 1
            daily_reset_at = daily_usage.get("reset_at", self._get_next_reset_time("daily"))
            if self._should_reset_counter(daily_reset_at, "daily"):
                daily_count = 1
                daily_reset_at = self._get_next_reset_time("daily")

            # Update monthly usage
            monthly_count = monthly_usage.get("count", 0) + 1
            monthly_reset_at = monthly_usage.get("reset_at", self._get_next_reset_time("monthly"))
            if self._should_reset_counter(monthly_reset_at, "monthly"):
                monthly_count = 1
                monthly_reset_at = self._get_next_reset_time("monthly")

            # Save updated usage
            user_ref.update({
                "usage.external_llm.daily": {"count": daily_count, "reset_at": daily_reset_at},
                "usage.external_llm.monthly": {"count": monthly_count, "reset_at": monthly_reset_at},
            })
            return True
        except Exception as e:
            logger.error(f"USAGE COUNTER ERROR - {str(e)}")
            return False

    def query_external_llm(
        self,
        prompt: str,
        model: Optional[str] = None,
        context: str = "",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
    ):
        """
        Send a prompt to the external LLM API with rate limiting and usage tracking.

        Args:
            prompt: The current user query or enhanced prompt
            model: The specific external LLM model to use. If None, defaults to config.
            context: Additional context from RAG
            conversation_history: List of previous messages in the conversation
            user_id: The user ID for rate limiting

        Returns:
            Dict with keys:
                response: The LLM's response text
                limits: Dict of limits
                usage: Dict of usage
                used_fallback: Bool
                fallback_reason: String if fallback used
        """
        # Rate limiting
        if user_id:
            rate_limit_info = self.check_rate_limits(user_id)
            if not rate_limit_info["allowed"]:
                if self.use_fallback:
                    # Use fallback model
                    fallback_result = self._use_fallback_model(
                        prompt, context, conversation_history, rate_limit_info
                    )
                    fallback_result["used_fallback"] = True
                    fallback_result["fallback_reason"] = rate_limit_info["reason"]
                    return fallback_result
                else:
                    return {
                        "success": False,
                        "error": rate_limit_info["reason"],
                        "used_fallback": False,
                        "limits": rate_limit_info.get("limits", {}),
                        "usage": rate_limit_info.get("usage", {}),
                    }
        # Prepare API request and send
        headers = {"Content-Type": "application/json"}
        contents = []
        if conversation_history:
            for message in conversation_history:
                contents.append({
                    "role": message["role"],
                    "parts": [{"text": message["content"]}],
                })
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.max_output_tokens,
            },
        }
        # Ensure the API URL has a scheme
        api_url = self.api_url
        if not api_url.startswith("http://") and not api_url.startswith("https://"):
            api_url = "https://" + api_url  # Default to https
        url = f"{api_url}?key={self.api_key}" if self.api_key else api_url
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(f"EXTERNAL LLM ERROR - HTTP {response.status_code}: {response.text}")
                return {"success": False, "error": response.text, "used_fallback": False}
            result = response.json()
            # Extract response text (Gemini format)
            response_text = result["candidates"][0]["content"]["parts"][0]["text"]
            # Update usage counters
            if user_id:
                self.update_usage_counters(user_id)
            return {
                "success": True,
                "response": response_text,
                "limits": {},
                "usage": {},
                "used_fallback": False,
            }
        except Exception as e:
            logger.error(f"EXTERNAL LLM ERROR - {str(e)}")
            return {"success": False, "error": str(e), "used_fallback": False}

    def _use_fallback_model(
        self,
        prompt: str,
        context: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        rate_limit_info: Optional[Dict[str, Any]] = None,
    ):
        """
        Use fallback model when rate limits are exceeded.
        """
        # This is a stub for fallback logic; you can implement Ollama or other fallback here.
        return {
            "success": False,
            "error": (
                "You have exceeded your API quota, and the fallback model failed to generate a response."
            ),
            "used_fallback": True,
            "limits": rate_limit_info.get("limits", {}) if rate_limit_info else {},
            "usage": rate_limit_info.get("usage", {}) if rate_limit_info else {},
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

# src/utils/retry_manager.py
import asyncio
import random
import time
from typing import Callable, Any, Optional
from loguru import logger
from .error_classifier import ErrorClassifier

class RetryManager:
    """Manages adaptive retry strategies based on error types."""

    def __init__(self):
        self.failure_counts = {}
        self.last_retry_times = {}

    async def execute_with_retry(
        self,
        step_func: Callable,
        step_name: str,
        max_retries: int = 3,
        context: dict = None,
        retry_after: float = None
    ) -> Any:
        """
        Execute a function with adaptive retry logic based on error classification.

        Args:
            step_func: Async function to execute
            step_name: Name of the step for logging
            max_retries: Maximum number of retry attempts
            context: Additional context for error handling

        Returns:
            Result of the successful execution

        Raises:
            Exception: The last exception if all retries fail
        """
        context = context or {}

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                start_time = time.time()
                result = await step_func()
                execution_time = time.time() - start_time

                # Success - reset failure count
                if step_name in self.failure_counts:
                    self.failure_counts[step_name] = 0

                logger.debug(f"✅ {step_name} succeeded (attempt {attempt + 1}, {execution_time:.2f}s)")
                return result

            except Exception as e:
                error_type = ErrorClassifier.classify_error(e)
                severity = ErrorClassifier.get_error_severity(error_type)

                # Update failure tracking
                self.failure_counts[step_name] = self.failure_counts.get(step_name, 0) + 1
                self.last_retry_times[step_name] = time.time()

                if attempt == max_retries:
                    # Final attempt failed
                    logger.error(f"❌ {step_name} failed permanently after {max_retries + 1} attempts: {error_type} - {str(e)}")
                    raise

                # Check if we should retry this error type
                if not ErrorClassifier.should_retry(error_type):
                    logger.warning(f"🚫 Not retrying {step_name} due to {error_type}: {str(e)}")
                    raise

                # Calculate delay with jitter
                retry_after = context.get("retry_after") if context else None
                delay = self._calculate_delay(error_type, attempt, context, retry_after)
                logger.warning(f"⚠️  {step_name} failed (attempt {attempt + 1}/{max_retries + 1}): {error_type} - retrying in {delay:.1f}s")

                await asyncio.sleep(delay)

    def _calculate_delay(self, error_type: str, attempt: int, context: dict, retry_after: float = None) -> float:
        """Calculate adaptive delay based on error type and context."""

        # If Retry-After header is provided, use it with some buffer
        if retry_after is not None and error_type == "rate_limit":
            return retry_after * 1.2  # Add 20% buffer

        # Base delays by error type (in seconds)
        base_delays = {
            # Network & Connection (quick retries)
            "dns_error": 2.0,
            "ssl_error": 3.0,
            "connection_error": 1.0,
            "network_unreachable": 5.0,

            # HTTP Status Codes
            "rate_limit": 60.0,      # Start with 1 minute for rate limits
            "server_error": 10.0,    # 10 seconds for 5xx errors
            "forbidden": 30.0,       # 30 seconds for 403
            "not_found": 0.0,        # No delay for 404

            # Browser/Automation
            "timeout": 5.0,
            "selector_not_found": 1.0,
            "stale_element": 0.5,
            "frame_error": 1.0,
            "dialog_error": 2.0,

            # Anti-Scraping
            "bot_detection": 120.0,   # 2 minutes for bot detection
            "captcha_detected": 300.0, # 5 minutes for CAPTCHA
            "ip_blocked": 600.0,      # 10 minutes for IP blocks

            # Content/Data
            "javascript_error": 2.0,
            "json_parse_error": 1.0,
            "encoding_error": 1.0,
            "ajax_error": 3.0,

            # System/Resource
            "memory_error": 10.0,
            "cpu_timeout": 5.0,
            "disk_space_error": 0.0,  # No delay, system issue

            # Other
            "page_load_error": 4.0,
            "data_extraction_error": 1.0,
            "websocket_error": 2.0,
            "race_condition": 1.0,
            "geo_blocked": 0.0,      # No delay, location issue
            "storage_error": 1.0,

            # Default
            "unknown": 2.0
        }

        base_delay = base_delays.get(error_type, 2.0)

        # For rate limiting, use exponential backoff with higher base
        if error_type == "rate_limit":
            exponential_delay = base_delay * (2 ** attempt)
        else:
            # For other errors, gentler exponential backoff
            exponential_delay = base_delay * (1.5 ** attempt)

        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.8, 1.2)
        delay = exponential_delay * jitter

        # Cap maximum delay at different levels based on error type
        max_delays = {
            "rate_limit": 1800.0,      # Max 30 minutes for rate limits
            "bot_detection": 3600.0,   # Max 1 hour for bot detection
            "ip_blocked": 7200.0,      # Max 2 hours for IP blocks
            "default": 300.0           # Max 5 minutes for others
        }

        max_delay = max_delays.get(error_type, max_delays["default"])
        return min(delay, max_delay)

    def get_failure_stats(self, step_name: str = None) -> dict:
        """Get failure statistics for monitoring."""
        if step_name:
            return {
                "failure_count": self.failure_counts.get(step_name, 0),
                "last_failure": self.last_retry_times.get(step_name)
            }

        return {
            "total_failures": sum(self.failure_counts.values()),
            "step_failures": self.failure_counts.copy(),
            "last_failures": self.last_retry_times.copy()
        }

    def reset_failure_count(self, step_name: str):
        """Reset failure count for a step (useful after successful recovery)."""
        if step_name in self.failure_counts:
            self.failure_counts[step_name] = 0
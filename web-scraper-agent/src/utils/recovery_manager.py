# src/utils/recovery_manager.py
import copy
from typing import Dict, Any
from loguru import logger

class RecoveryManager:
    """Provides fallback recovery strategies when steps fail."""

    @staticmethod
    def get_fallback_strategy(error_type: str, original_step: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate a fallback strategy based on error type and original step.

        Args:
            error_type: Classified error type
            original_step: The original failing step
            context: Additional context (tech_info, etc.)

        Returns:
            Modified step with fallback strategy
        """
        context = context or {}
        fallback_step = copy.deepcopy(original_step)

        strategy_map = {
            "selector_not_found": RecoveryManager._broaden_selectors,
            "timeout": RecoveryManager._add_timeouts,
            "bot_detection": RecoveryManager._switch_to_api_mode,
            "javascript_error": RecoveryManager._simplify_javascript,
            "page_load_error": RecoveryManager._add_wait_conditions,
            "network_error": RecoveryManager._add_retry_logic,
            "rate_limit": RecoveryManager._handle_rate_limit,
            "dns_error": RecoveryManager._handle_dns_error,
            "ssl_error": RecoveryManager._handle_ssl_error,
            "connection_error": RecoveryManager._handle_connection_error,
            "server_error": RecoveryManager._handle_server_error,
            "memory_error": RecoveryManager._handle_memory_error,
            "encoding_error": RecoveryManager._handle_encoding_error,
            "json_parse_error": RecoveryManager._handle_json_error,
            "stale_element": RecoveryManager._handle_stale_element,
            "frame_error": RecoveryManager._handle_frame_error,
            "dialog_error": RecoveryManager._handle_dialog_error,
            "ajax_error": RecoveryManager._handle_ajax_error,
            "cpu_timeout": RecoveryManager._handle_cpu_timeout,
        }

        strategy_func = strategy_map.get(error_type, RecoveryManager._default_fallback)
        return strategy_func(fallback_step, context)

    @staticmethod
    def _broaden_selectors(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Broaden selectors to be more inclusive when original selectors fail."""
        if step.get("action") in ["click", "fill", "extract"]:
            original_selector = step.get("selector", "")

            # Add broader fallback selectors
            broader_selectors = [
                original_selector,
                original_selector.replace("#", "."),  # Try class instead of ID
                original_selector.replace(".", ""),   # Try without class
                f"[data-testid*='{step.get('element', '')}']",  # Try data attributes
                f"[aria-label*='{step.get('element', '')}']",    # Try aria labels
            ]

            # Remove empty selectors and duplicates
            broader_selectors = list(set(sel for sel in broader_selectors if sel))

            if len(broader_selectors) > 1:
                step["fallback_selectors"] = broader_selectors[1:]
                logger.info(f"🔄 Broadened selectors for {step.get('comment', 'step')}: {broader_selectors}")

        return step

    @staticmethod
    def _add_timeouts(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Add longer timeouts and waits for timeout errors."""
        # Increase existing timeout or add one
        if "timeout" in step:
            step["timeout"] = min(step["timeout"] * 1.5, 30000)  # Max 30 seconds
        else:
            step["timeout"] = 10000  # 10 seconds default

        # Add wait conditions for dynamic content
        if step.get("action") == "extract" and context.get("spa"):
            step["wait_for"] = "networkidle"  # Wait for network to be idle
        elif step.get("action") == "extract":
            step["wait_for"] = "domcontentloaded"

        logger.info(f"⏱️  Added timeout handling for {step.get('comment', 'step')}: {step.get('timeout')}ms")
        return step

    @staticmethod
    def _switch_to_api_mode(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Switch to API-based extraction when bot detection occurs."""
        if step.get("action") == "extract" and context.get("api_endpoints"):
            # Modify step to use API instead of browser extraction
            step["action"] = "api_extract"
            step["api_endpoint"] = context["api_endpoints"][0]  # Use first available endpoint
            step["comment"] = f"{step.get('comment', 'Extract')} (API fallback)"
            logger.info(f"🔌 Switched to API mode for {step.get('comment', 'step')}")
        else:
            # Add longer delays and stealth mode
            step["stealth_mode"] = True
            step["delay"] = 5000  # 5 second delay
            logger.info(f"🕵️  Enabled stealth mode for {step.get('comment', 'step')}")

        return step

    @staticmethod
    def _simplify_javascript(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Simplify JavaScript when JS errors occur."""
        if step.get("action") == "extract":
            # Use simpler extraction logic
            original_fields = step.get("fields", {})
            simplified_fields = {}

            for field_name, selector in original_fields.items():
                if field_name in ["title", "text", "content"]:
                    # Use broader, simpler selectors
                    simplified_fields[field_name] = "h1, h2, h3, p, div, span"
                else:
                    simplified_fields[field_name] = selector

            step["fields"] = simplified_fields
            step["simplified"] = True
            logger.info(f"🔧 Simplified JavaScript extraction for {step.get('comment', 'step')}")

        return step

    @staticmethod
    def _add_wait_conditions(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Add wait conditions for page load errors."""
        step["wait_until"] = "networkidle"
        step["timeout"] = 15000  # 15 seconds

        if context.get("spa"):
            step["wait_for_selector"] = "body[data-loaded], main, .content"

        logger.info(f"⏳ Added wait conditions for {step.get('comment', 'step')}")
        return step

    @staticmethod
    def _add_retry_logic(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Add retry logic for network errors."""
        step["retry_count"] = 3
        step["retry_delay"] = 2000  # 2 seconds
        logger.info(f"🔄 Added retry logic for {step.get('comment', 'step')}")
        return step

    @staticmethod
    def _handle_rate_limit(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle rate limiting (HTTP 429) with exponential backoff."""
        step["rate_limited"] = True
        step["delay"] = min(300, 30 * (2 ** (context.get("retry_count", 0))))  # Max 5 minutes
        step["use_proxy"] = True  # Suggest using different IP
        step["user_agent_rotation"] = True
        logger.info(f"🐌 Rate limited - adding {step['delay']}s delay and proxy rotation")
        return step

    @staticmethod
    def _handle_dns_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle DNS resolution failures."""
        step["dns_retry"] = True
        step["timeout"] = 30000  # 30 seconds for DNS
        step["use_alternate_dns"] = True
        logger.info("🌐 DNS error - extending timeout and suggesting alternate DNS")
        return step

    @staticmethod
    def _handle_ssl_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SSL/TLS certificate errors."""
        step["ignore_ssl_errors"] = True  # For testing only
        step["ssl_retry"] = True
        logger.warning("🔒 SSL error - ignoring certificate validation (use with caution)")
        return step

    @staticmethod
    def _handle_connection_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle connection refused/reset errors."""
        step["connection_retry"] = True
        step["timeout"] = 20000  # 20 seconds
        step["retry_delay"] = 5000  # 5 second delay between retries
        logger.info("🔌 Connection error - adding retry logic with delays")
        return step

    @staticmethod
    def _handle_server_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle 5xx server errors."""
        step["server_error_retry"] = True
        step["retry_delay"] = 10000  # 10 seconds for server errors
        step["max_server_retries"] = 2  # Limited retries for server errors
        logger.info("🖥️  Server error - adding longer delays and limited retries")
        return step

    @staticmethod
    def _handle_memory_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle browser memory exhaustion."""
        step["restart_browser"] = True
        step["reduce_concurrency"] = True
        step["clear_cache"] = True
        logger.warning("🧠 Memory error - recommending browser restart and reduced concurrency")
        return step

    @staticmethod
    def _handle_encoding_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle character encoding issues."""
        step["encoding_fallback"] = True
        step["try_encodings"] = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
        logger.info("🔤 Encoding error - adding encoding fallback attempts")
        return step

    @staticmethod
    def _handle_json_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JSON parsing failures."""
        step["json_fallback"] = True
        step["skip_malformed_json"] = True
        logger.info("📄 JSON parse error - adding malformed JSON handling")
        return step

    @staticmethod
    def _handle_stale_element(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle stale element references."""
        step["stale_element_retry"] = True
        step["refind_element"] = True
        step["wait_before_refind"] = 1000  # 1 second
        logger.info("👻 Stale element - adding refind logic")
        return step

    @staticmethod
    def _handle_frame_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle iframe access errors."""
        step["frame_fallback"] = True
        step["try_main_frame_first"] = True
        logger.info("🖼️  Frame error - adding main frame fallback")
        return step

    @staticmethod
    def _handle_dialog_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle unexpected dialogs/popups."""
        step["auto_dismiss_dialogs"] = True
        step["dialog_timeout"] = 5000  # 5 seconds to handle dialogs
        logger.info("💬 Dialog error - adding auto-dismiss logic")
        return step

    @staticmethod
    def _handle_ajax_error(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle AJAX/dynamic content loading issues."""
        step["ajax_retry"] = True
        step["wait_for_ajax"] = True
        step["ajax_timeout"] = 10000  # 10 seconds for AJAX
        logger.info("📡 AJAX error - adding AJAX wait conditions")
        return step

    @staticmethod
    def _handle_cpu_timeout(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle script execution timeouts."""
        step["cpu_timeout_retry"] = True
        step["simplify_processing"] = True
        step["script_timeout"] = 30000  # 30 seconds
        logger.info("⚡ CPU timeout - simplifying processing and extending timeout")
        return step

    @staticmethod
    def _default_fallback(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Default fallback strategy for unhandled error types."""
        step["fallback_attempted"] = True
        step["retry_count"] = min(step.get("retry_count", 0) + 1, 3)  # Max 3 retries
        step["retry_delay"] = 2000  # 2 second delay
        logger.info(f"🔄 Default fallback for {step.get('comment', 'step')} - adding basic retry logic")
        return step

    @staticmethod
    def should_attempt_recovery(error_type: str, attempt_count: int) -> bool:
        """Determine if recovery should be attempted."""
        # Never attempt recovery for these critical errors
        no_recovery_types = [
            "memory_error",      # System-level issue
            "disk_space_error",  # System-level issue
            "ip_blocked",        # Requires IP change
            "geo_blocked",       # Requires location change
            "forbidden",         # Access denied permanently
            "not_found",         # Resource doesn't exist
        ]

        # Limited recovery attempts for these
        limited_recovery_types = [
            "bot_detection",     # Only try API fallback once
            "captcha_detected",  # Only try once
            "dns_error",         # DNS issues might resolve quickly
            "ssl_error",         # SSL issues usually permanent
        ]

        if error_type in no_recovery_types:
            return False

        if error_type in limited_recovery_types and attempt_count > 1:
            return False

        # For server errors, don't attempt recovery after 3 failures
        if error_type == "server_error" and attempt_count > 3:
            return False

        # For rate limiting, don't attempt recovery after 5 failures
        if error_type == "rate_limit" and attempt_count > 5:
            return False

        return True
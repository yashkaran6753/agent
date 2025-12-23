# src/utils/error_classifier.py
from playwright._impl._errors import TimeoutError, Error as PlaywrightError
import re

class ErrorClassifier:
    """Classifies errors into categories for appropriate handling strategies."""

    @staticmethod
    def classify_error(error: Exception) -> str:
        """Classify an exception into a category for targeted handling."""
        error_msg = str(error).lower()
        error_type = type(error).__name__

        # Network & Connection Errors
        if any(keyword in error_msg for keyword in ["dns", "name resolution", "nodename nor servname"]):
            return "dns_error"
        if "ssl" in error_msg or "tls" in error_msg or "certificate" in error_msg:
            return "ssl_error"
        if "connection refused" in error_msg or "connection reset" in error_msg:
            return "connection_error"
        if "network" in error_msg and "unreachable" in error_msg:
            return "network_unreachable"

        # HTTP Status Code Errors
        if "429" in error_msg or "too many requests" in error_msg or "rate limit" in error_msg:
            return "rate_limit"
        if "403" in error_msg or "forbidden" in error_msg:
            return "forbidden"
        if "404" in error_msg or "not found" in error_msg:
            return "not_found"
        if "500" in error_msg or "502" in error_msg or "503" in error_msg or "504" in error_msg:
            return "server_error"

        # Browser/Automation Errors
        if isinstance(error, TimeoutError) or "timeout" in error_msg:
            return "timeout"
        if "selector" in error_msg or "element" in error_msg or "locator" in error_msg:
            return "selector_not_found"
        if "stale" in error_msg and "element" in error_msg:
            return "stale_element"
        if "frame" in error_msg and ("not found" in error_msg or "detached" in error_msg):
            return "frame_error"
        if "dialog" in error_msg or "alert" in error_msg or "popup" in error_msg:
            return "dialog_error"

        # Anti-Scraping/Bot Detection Errors
        if any(keyword in error_msg for keyword in ["captcha", "recaptcha", "hcaptcha"]):
            return "captcha_detected"
        if any(keyword in error_msg for keyword in ["cloudflare", "challenge", "verification"]):
            return "bot_detection"
        if "blocked" in error_msg or "banned" in error_msg:
            return "ip_blocked"

        # Content & Data Extraction Errors
        if "json" in error_msg and ("parse" in error_msg or "decode" in error_msg):
            return "json_parse_error"
        if "encoding" in error_msg or "charset" in error_msg or "unicode" in error_msg:
            return "encoding_error"
        if "javascript" in error_msg or "script" in error_msg or "eval" in error_msg:
            return "javascript_error"

        # Resource & Performance Errors
        if "memory" in error_msg or "out of memory" in error_msg:
            return "memory_error"
        if "cpu" in error_msg or "timeout" in error_msg and "script" in error_msg:
            return "cpu_timeout"
        if "disk" in error_msg or "space" in error_msg:
            return "disk_space_error"

        # Dynamic Content & Timing Errors
        if "ajax" in error_msg or "xhr" in error_msg or "fetch" in error_msg:
            return "ajax_error"
        if "websocket" in error_msg:
            return "websocket_error"
        if "race" in error_msg or "timing" in error_msg:
            return "race_condition"

        # Geographic & Localization Errors
        if any(keyword in error_msg for keyword in ["geo", "region", "location", "blocked"]):
            return "geo_blocked"
        if "cookie" in error_msg or "localstorage" in error_msg:
            return "storage_error"

        # Default fallback
        return "unknown"

    @staticmethod
    def get_error_severity(error_type: str) -> str:
        """Get severity level for an error type."""
        severity_map = {
            # Critical - usually unrecoverable or require major intervention
            "bot_detection": "critical",
            "ip_blocked": "critical",
            "geo_blocked": "critical",
            "memory_error": "critical",
            "disk_space_error": "critical",

            # High - significant issues requiring attention
            "dns_error": "high",
            "ssl_error": "high",
            "connection_error": "high",
            "server_error": "high",
            "rate_limit": "high",
            "forbidden": "high",
            "captcha_detected": "high",

            # Medium - recoverable with retries/adjustments
            "timeout": "medium",
            "network_unreachable": "medium",
            "page_load_error": "medium",
            "javascript_error": "medium",
            "json_parse_error": "medium",
            "encoding_error": "medium",
            "cpu_timeout": "medium",

            # Low - usually recoverable with simple changes
            "selector_not_found": "low",
            "stale_element": "low",
            "frame_error": "low",
            "dialog_error": "low",
            "not_found": "low",
            "data_extraction_error": "low",
            "ajax_error": "low",
            "websocket_error": "low",
            "race_condition": "low",
            "storage_error": "low",

            # Default
            "unknown": "medium"
        }
        return severity_map.get(error_type, "medium")

    @staticmethod
    def should_retry(error_type: str) -> bool:
        """Determine if an error type should trigger a retry."""
        # Never retry these error types - they require intervention
        no_retry_types = [
            "bot_detection",      # Don't retry bot detection
            "ip_blocked",         # IP is blocked, need different IP
            "geo_blocked",        # Geographic blocking
            "captcha_detected",   # Manual CAPTCHA solving needed
            "forbidden",          # 403 Forbidden - access denied
            "not_found",          # 404 - resource doesn't exist
            "memory_error",       # System memory issues
            "disk_space_error",   # No disk space
        ]

        # Limited retries for these (only 1-2 attempts)
        limited_retry_types = [
            "dns_error",          # DNS issues might resolve
            "ssl_error",          # SSL issues might be temporary
            "server_error",       # 5xx errors might be temporary
        ]

        if error_type in no_retry_types:
            return False
        elif error_type in limited_retry_types:
            return True  # But with limited attempts
        else:
            return True   # Default to retry for most errors
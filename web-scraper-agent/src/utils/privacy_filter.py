# src/utils/privacy_filter.py
import re
import hashlib
from typing import Dict, List, Any, Union
from loguru import logger

class PrivacyFilter:
    """Filters and redacts personally identifiable information from extracted data."""

    def __init__(self):
        # Email patterns
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

        # Phone number patterns (various formats)
        self.phone_patterns = [
            re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),  # US format: 123-456-7890
            re.compile(r'\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b'),  # (123) 456-7890
            re.compile(r'\b\d{10,11}\b'),  # 10-11 digits
            re.compile(r'\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,4}'),  # International
        ]

        # Social Security Number patterns
        self.ssn_pattern = re.compile(r'\b\d{3}[-]?\d{2}[-]?\d{4}\b')

        # Credit card patterns (basic detection)
        self.cc_pattern = re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b')

        # IP address patterns
        self.ip_pattern = re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b')

        # Names (basic detection - capitalized words that could be names)
        self.name_pattern = re.compile(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b')

        # Addresses (street addresses)
        self.address_pattern = re.compile(r'\b\d+\s+[A-Za-z0-9\s,.-]+\b')

        # API keys and tokens (generic patterns)
        self.api_key_patterns = [
            re.compile(r'\b[A-Za-z0-9]{32,}\b'),  # Long alphanumeric strings
            re.compile(r'\b[A-Za-z0-9+/=]{20,}\b'),  # Base64-like strings
        ]

    def filter_data(self, data: Union[Dict, List, str], redact: bool = True) -> Union[Dict, List, str]:
        """
        Filter PII from extracted data.

        Args:
            data: The data to filter (dict, list, or string)
            redact: If True, redact PII; if False, just detect and log

        Returns:
            Filtered data with PII redacted or flagged
        """
        if isinstance(data, dict):
            return self._filter_dict(data, redact)
        elif isinstance(data, list):
            return self._filter_list(data, redact)
        elif isinstance(data, str):
            return self._filter_string(data, redact)
        else:
            return data

    def _filter_dict(self, data: Dict[str, Any], redact: bool) -> Dict[str, Any]:
        """Filter PII from dictionary data."""
        filtered = {}
        for key, value in data.items():
            # Skip certain fields that commonly contain PII
            if self._is_sensitive_field(key):
                if redact:
                    filtered[key] = self._redact_value(value)
                    logger.warning(f"🔒 Redacted sensitive field: {key}")
                else:
                    filtered[key] = value
                    logger.warning(f"⚠️ Detected sensitive field: {key}")
            else:
                filtered[key] = self.filter_data(value, redact)
        return filtered

    def _filter_list(self, data: List[Any], redact: bool) -> List[Any]:
        """Filter PII from list data."""
        return [self.filter_data(item, redact) for item in data]

    def _filter_string(self, text: str, redact: bool) -> str:
        """Filter PII from string data."""
        if not isinstance(text, str):
            return text

        original_text = text

        # Apply all PII patterns
        pii_patterns = [
            ('email', self.email_pattern),
            ('phone', self.phone_patterns[0]),  # Just use first phone pattern for demo
            ('ssn', self.ssn_pattern),
            ('credit_card', self.cc_pattern),
            ('ip_address', self.ip_pattern),
        ]

        for pii_type, pattern in pii_patterns:
            text = self._apply_pattern(text, pattern, pii_type, redact)

        if text != original_text and not redact:
            logger.warning("⚠️ PII detected in text content")

        return text

    def _apply_pattern(self, text: str, pattern: re.Pattern, pii_type: str, redact: bool) -> str:
        """Apply a PII detection/redaction pattern."""
        def replace_func(match):
            if redact:
                return f"[REDACTED_{pii_type.upper()}]"
            else:
                logger.warning(f"⚠️ Detected {pii_type}: {match.group()}")
                return match.group()

        return pattern.sub(replace_func, text)

    def _is_sensitive_field(self, field_name: str) -> bool:
        """Check if a field name indicates sensitive data."""
        sensitive_fields = {
            'email', 'phone', 'mobile', 'telephone', 'cell',
            'ssn', 'social_security', 'socialsecurity',
            'credit_card', 'cc_number', 'card_number',
            'password', 'passwd', 'pwd',
            'token', 'api_key', 'apikey', 'auth_token',
            'session_id', 'sessionid',
            'ip_address', 'ip',
            'address', 'home_address', 'billing_address',
            'name', 'full_name', 'first_name', 'last_name',
            'dob', 'date_of_birth', 'birth_date',
            'user_id', 'userid', 'customer_id'
        }

        field_lower = field_name.lower().replace('_', '').replace('-', '')
        return field_lower in sensitive_fields

    def _redact_value(self, value: Any) -> str:
        """Redact a sensitive value."""
        if isinstance(value, str):
            # Create a hash-based redaction that's consistent for the same value
            # but doesn't reveal the actual content
            hash_obj = hashlib.sha256(str(value).encode())
            hash_short = hash_obj.hexdigest()[:8]
            return f"[REDACTED_{hash_short}]"
        else:
            return "[REDACTED]"

    def scan_for_pii(self, data: Union[Dict, List, str]) -> List[str]:
        """
        Scan data for PII without redacting, returning types found.

        Returns:
            List of PII types detected
        """
        pii_types = []

        def scan_recursive(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if self._is_sensitive_field(key):
                        pii_types.append(f"sensitive_field_{key}")
                    scan_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    scan_recursive(item)
            elif isinstance(obj, str):
                # Quick scan for patterns
                if self.email_pattern.search(obj):
                    pii_types.append("email")
                for pattern in self.phone_patterns:
                    if pattern.search(obj):
                        pii_types.append("phone")
                        break
                if self.ssn_pattern.search(obj):
                    pii_types.append("ssn")
                if self.cc_pattern.search(obj):
                    pii_types.append("credit_card")

        scan_recursive(data)
        return list(set(pii_types))  # Remove duplicates
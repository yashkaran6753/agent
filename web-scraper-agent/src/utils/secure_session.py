# src/utils/secure_session.py
import json
import base64
import hashlib
import os
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger

class SecureSessionStorage:
    """Secure storage for browser sessions with encryption and credential filtering."""

    def __init__(self, sessions_dir: Path = None):
        self.sessions_dir = sessions_dir or Path("sessions")
        self.sessions_dir.mkdir(exist_ok=True)
        self._key = None

    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key."""
        if self._key is None:
            # Use a consistent key derived from environment or generate one
            key_seed = os.getenv("SESSION_ENCRYPTION_KEY", "default_session_key")
            salt = b'session_salt_2024'  # Consistent salt

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            self._key = base64.urlsafe_b64encode(kdf.derive(key_seed.encode()))

        return self._key

    def _encrypt_data(self, data: str) -> str:
        """Encrypt session data."""
        try:
            f = Fernet(self._get_encryption_key())
            return f.encrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt session data: {e}")
            return data  # Fallback to unencrypted

    def _decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt session data."""
        try:
            f = Fernet(self._get_encryption_key())
            return f.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt session data: {e}")
            return encrypted_data  # Fallback to encrypted data

    def filter_sensitive_session_data(self, session_data: dict) -> dict:
        """
        Filter out sensitive information from session data before storage.

        Args:
            session_data: Raw session data from browser

        Returns:
            Filtered session data safe for storage
        """
        if not isinstance(session_data, dict):
            return session_data

        filtered = {}

        # Safe top-level keys to keep
        safe_keys = {
            'cookies', 'origins', 'localStorage', 'sessionStorage',
            'indexedDB', 'webSQL', 'serviceWorkers', 'cacheStorage'
        }

        for key, value in session_data.items():
            if key in safe_keys:
                if key == 'cookies':
                    # Filter cookies to remove sensitive ones
                    filtered[key] = self._filter_cookies(value)
                elif key in ['localStorage', 'sessionStorage']:
                    # Filter storage to remove sensitive data
                    filtered[key] = self._filter_storage(value)
                else:
                    # Keep other safe data as-is
                    filtered[key] = value
            else:
                # Log and skip unknown/sensitive keys
                logger.debug(f"Skipping potentially sensitive session key: {key}")

        return filtered

    def _filter_cookies(self, cookies: list) -> list:
        """Filter cookies to remove sensitive authentication cookies."""
        if not isinstance(cookies, list):
            return cookies

        sensitive_cookie_names = {
            'session', 'sessionid', 'auth', 'token', 'jwt', 'bearer',
            'login', 'password', 'passwd', 'credential', 'secret',
            'api_key', 'apikey', 'access_token', 'refresh_token'
        }

        filtered_cookies = []
        for cookie in cookies:
            if isinstance(cookie, dict):
                cookie_name = cookie.get('name', '').lower()
                # Skip sensitive cookies
                if any(sensitive in cookie_name for sensitive in sensitive_cookie_names):
                    logger.warning(f"🔒 Filtered sensitive cookie: {cookie_name}")
                    continue

                # Remove sensitive cookie attributes
                safe_cookie = {k: v for k, v in cookie.items()
                             if k not in ['httpOnly', 'secure', 'sameSite']}
                filtered_cookies.append(safe_cookie)
            else:
                filtered_cookies.append(cookie)

        return filtered_cookies

    def _filter_storage(self, storage_data: list) -> list:
        """Filter local/session storage to remove sensitive data."""
        if not isinstance(storage_data, list):
            return storage_data

        sensitive_keys = {
            'token', 'auth', 'session', 'password', 'secret', 'key',
            'credential', 'login', 'user', 'email', 'phone'
        }

        filtered_storage = []
        for item in storage_data:
            if isinstance(item, dict):
                key = item.get('name', '').lower()
                # Skip sensitive storage keys
                if any(sensitive in key for sensitive in sensitive_keys):
                    logger.warning(f"🔒 Filtered sensitive storage key: {key}")
                    continue

                filtered_storage.append(item)
            else:
                filtered_storage.append(item)

        return filtered_storage

    def save_session(self, domain: str, session_data: dict):
        """
        Save filtered and encrypted session data.

        Args:
            domain: Domain name for the session file
            session_data: Raw session data from browser
        """
        try:
            # Filter sensitive data
            filtered_data = self.filter_sensitive_session_data(session_data)

            # Convert to JSON
            json_data = json.dumps(filtered_data, indent=2)

            # Encrypt the data
            encrypted_data = self._encrypt_data(json_data)

            # Save to file
            session_file = self.sessions_dir / f"{domain}.json"
            with open(session_file, 'w', encoding='utf-8') as f:
                f.write(encrypted_data)

            logger.info(f"🔐 Securely saved session for {domain}")

        except Exception as e:
            logger.error(f"Failed to save session for {domain}: {e}")

    def load_session(self, domain: str) -> dict:
        """
        Load and decrypt session data.

        Args:
            domain: Domain name for the session file

        Returns:
            Decrypted session data or empty dict if not found
        """
        try:
            session_file = self.sessions_dir / f"{domain}.json"
            if not session_file.exists():
                return {}

            # Read encrypted data
            with open(session_file, 'r', encoding='utf-8') as f:
                encrypted_data = f.read()

            # Decrypt
            json_data = self._decrypt_data(encrypted_data)

            # Parse JSON
            return json.loads(json_data)

        except Exception as e:
            logger.error(f"Failed to load session for {domain}: {e}")
            return {}

    def delete_session(self, domain: str):
        """Delete a stored session."""
        try:
            session_file = self.sessions_dir / f"{domain}.json"
            if session_file.exists():
                session_file.unlink()
                logger.info(f"🗑️ Deleted session for {domain}")
        except Exception as e:
            logger.error(f"Failed to delete session for {domain}: {e}")

    def list_sessions(self) -> list:
        """List all stored session domains."""
        try:
            return [f.stem for f in self.sessions_dir.glob("*.json")]
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []
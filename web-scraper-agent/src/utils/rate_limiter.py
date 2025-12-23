# src/utils/rate_limiter.py
import asyncio
import time
from collections import defaultdict
from urllib.parse import urlparse
from loguru import logger

class RateLimiter:
    """Domain-aware rate limiter with polite crawling delays."""

    def __init__(self):
        # Domain -> list of request timestamps
        self.request_history = defaultdict(list)
        # Domain -> current delay between requests
        self.domain_delays = defaultdict(float)
        # Domain -> last request time
        self.last_request_time = defaultdict(float)
        # Global rate limiting
        self.global_last_request = 0.0
        self.global_min_delay = 1.0  # Minimum 1 second between any requests

    def set_domain_delay(self, domain: str, delay_seconds: float):
        """Set the minimum delay between requests for a specific domain."""
        self.domain_delays[domain] = max(delay_seconds, 0.1)  # Minimum 100ms
        logger.info(f"⏱️ Set domain delay for {domain}: {delay_seconds}s")

    def update_from_retry_after(self, domain: str, retry_after_seconds: float):
        """Update domain delay based on Retry-After header."""
        current_delay = self.domain_delays[domain]
        # Use the larger of current delay or retry-after, with some buffer
        new_delay = max(current_delay, retry_after_seconds * 1.2)
        self.set_domain_delay(domain, new_delay)
        logger.warning(f"🔄 Updated delay for {domain} due to Retry-After: {new_delay}s")

    async def wait_if_needed(self, url: str):
        """Wait if necessary to respect rate limits for the given URL."""
        domain = self._extract_domain(url)
        now = time.time()

        # Global rate limiting
        global_wait = max(0, self.global_min_delay - (now - self.global_last_request))
        if global_wait > 0:
            logger.debug(f"🌐 Global rate limit: waiting {global_wait:.2f}s")
            await asyncio.sleep(global_wait)

        # Domain-specific rate limiting
        domain_delay = self.domain_delays[domain]
        last_domain_request = self.last_request_time[domain]

        if domain_delay > 0:
            domain_wait = max(0, domain_delay - (now - last_domain_request))
            if domain_wait > 0:
                logger.debug(f"🏢 Domain rate limit for {domain}: waiting {domain_wait:.2f}s")
                await asyncio.sleep(domain_wait)

        # Update timestamps
        self.last_request_time[domain] = time.time()
        self.global_last_request = time.time()

        # Track request history (keep last 100 requests per domain)
        self.request_history[domain].append(now)
        if len(self.request_history[domain]) > 100:
            self.request_history[domain].pop(0)

    def get_domain_stats(self, domain: str) -> dict:
        """Get rate limiting statistics for a domain."""
        history = self.request_history[domain]
        if not history:
            return {"requests_last_minute": 0, "current_delay": self.domain_delays[domain]}

        now = time.time()
        recent_requests = [t for t in history if now - t < 60]  # Last minute

        return {
            "requests_last_minute": len(recent_requests),
            "current_delay": self.domain_delays[domain],
            "total_requests": len(history)
        }

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return "unknown"

    def set_polite_delay(self, domain: str, requests_per_minute: int = 30):
        """Set a polite delay based on desired requests per minute."""
        if requests_per_minute <= 0:
            delay = 0.1  # Minimum delay
        else:
            delay = 60.0 / requests_per_minute

        self.set_domain_delay(domain, delay)
        logger.info(f"🤝 Set polite delay for {domain}: {delay:.2f}s ({requests_per_minute} req/min)")
# src/utils/error_detector.py
from playwright.async_api import Page
from loguru import logger
from typing import List, Dict, Any

class ProactiveErrorDetector:
    """Proactively detects potential scraping issues before they cause errors."""

    @staticmethod
    async def detect_impending_errors(page: Page, tech_info: Dict[str, Any] = None) -> List[str]:
        """
        Proactively check for common issues that might cause errors.

        Returns a list of warning types detected.
        """
        warnings = []
        tech_info = tech_info or {}

        try:
            # Check for Cloudflare/anti-bot protection
            cloudflare_detected = await page.evaluate("""
                () => {
                    return !!document.querySelector('#challenge-form, .cf-browser-verification, #cf-challenge-running, .cf-error-details');
                }
            """)
            if cloudflare_detected:
                warnings.append("cloudflare_protection")
                logger.warning("🛡️ Cloudflare protection detected")

            # Check for other bot detection systems
            bot_detection = await page.evaluate("""
                () => {
                    return !!document.querySelector('[class*="recaptcha"], [id*="recaptcha"], [class*="hcaptcha"], [id*="hcaptcha"]');
                }
            """)
            if bot_detection:
                warnings.append("captcha_system")
                logger.warning("🤖 CAPTCHA system detected")

            # Check memory usage (if available)
            try:
                memory_usage = await page.evaluate("""
                    () => {
                        return performance.memory?.usedJSHeapSize || 0;
                    }
                """)
                if memory_usage > 500000000:  # 500MB
                    warnings.append("high_memory_usage")
                    logger.warning(f"🧠 High memory usage detected: {memory_usage / 1024 / 1024:.1f}MB")
            except:
                pass  # Memory API not available

            # Check for heavy JavaScript
            script_count = tech_info.get("script_count", 0)
            if script_count > 50:
                warnings.append("heavy_javascript")
                logger.warning(f"⚡ Heavy JavaScript detected: {script_count} scripts")

            # Check for rate limiting indicators
            rate_limit_indicators = await page.evaluate("""
                () => {
                    const text = document.body.textContent.toLowerCase();
                    return text.includes('rate limit') || text.includes('too many requests') || text.includes('429');
                }
            """)
            if rate_limit_indicators:
                warnings.append("rate_limit_indicators")
                logger.warning("🐌 Rate limiting indicators detected in page content")

            # Check for geographic restrictions
            geo_indicators = await page.evaluate("""
                () => {
                    const text = document.body.textContent.toLowerCase();
                    return text.includes('geographic') || text.includes('region') || text.includes('location blocked');
                }
            """)
            if geo_indicators:
                warnings.append("geographic_restrictions")
                logger.warning("🌍 Geographic restrictions detected")

            # Check for maintenance pages
            maintenance_indicators = await page.evaluate("""
                () => {
                    const text = document.body.textContent.toLowerCase();
                    return text.includes('maintenance') || text.includes('temporarily unavailable') || text.includes('down for maintenance');
                }
            """)
            if maintenance_indicators:
                warnings.append("maintenance_mode")
                logger.warning("🔧 Site appears to be in maintenance mode")

            # Check for very slow loading (basic heuristic)
            load_time = await page.evaluate("""
                () => {
                    return performance.timing.loadEventEnd - performance.timing.navigationStart;
                }
            """)
            if load_time > 30000:  # 30 seconds
                warnings.append("slow_loading")
                logger.warning(f"🐌 Very slow page load detected: {load_time/1000:.1f}s")

        except Exception as e:
            logger.debug(f"Error during proactive detection: {e}")
            warnings.append("detection_error")

        return warnings

    @staticmethod
    async def get_prevention_recommendations(warnings: List[str]) -> Dict[str, Any]:
        """Get prevention recommendations based on detected warnings."""

        recommendations = {
            "use_proxy": False,
            "add_delays": False,
            "stealth_mode": False,
            "reduce_concurrency": False,
            "use_api_fallback": False,
            "skip_heavy_pages": False,
            "geographic_workaround": False,
            "maintenance_wait": False,
        }

        for warning in warnings:
            if warning in ["cloudflare_protection", "captcha_system"]:
                recommendations["use_proxy"] = True
                recommendations["stealth_mode"] = True
                recommendations["add_delays"] = True

            elif warning == "rate_limit_indicators":
                recommendations["add_delays"] = True
                recommendations["reduce_concurrency"] = True

            elif warning == "high_memory_usage":
                recommendations["reduce_concurrency"] = True
                recommendations["skip_heavy_pages"] = True

            elif warning == "heavy_javascript":
                recommendations["add_delays"] = True

            elif warning == "geographic_restrictions":
                recommendations["geographic_workaround"] = True
                recommendations["use_proxy"] = True

            elif warning == "maintenance_mode":
                recommendations["maintenance_wait"] = True

            elif warning == "slow_loading":
                recommendations["add_delays"] = True
                recommendations["use_api_fallback"] = True

        return recommendations

    @staticmethod
    def should_proceed_with_scraping(warnings: List[str]) -> bool:
        """Determine if scraping should proceed based on warnings."""

        # Critical warnings that should stop scraping
        critical_warnings = [
            "maintenance_mode",  # Site is down
            "geographic_restrictions",  # Completely blocked
        ]

        # High-risk warnings that require special handling
        high_risk_warnings = [
            "cloudflare_protection",  # Very difficult to bypass
            "captcha_system",  # Requires manual intervention
        ]

        if any(warning in critical_warnings for warning in warnings):
            return False

        if len([w for w in warnings if w in high_risk_warnings]) > 1:
            return False  # Multiple high-risk warnings

        return True  # Safe to proceed
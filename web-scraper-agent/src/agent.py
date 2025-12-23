# src/agent.py (All 5 features integrated)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
import os, json, time, asyncio, sys
from dotenv import load_dotenv  # Added: Load .env early
load_dotenv()  # Load .env for all os.getenv calls

import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message="Caught.*compiling regex")
from loguru import logger
from playwright.async_api import async_playwright
from playwright.async_api import Page
from urllib import robotparser
from urllib.parse import urlparse, urljoin
import time
from src.browser_pool import BrowserPool
from src.azure_llm import ask_llm, tk
from src.prompts.clarifier import CLARIFIER
from src.prompts.planner import PLANNER
from src.content_saver import save
from jinja2 import Template
from src.utils.state import AgentState
from src.utils.api_interceptor import APIInterceptor
from src.utils.error_classifier import ErrorClassifier
from src.utils.retry_manager import RetryManager
from src.utils.recovery_manager import RecoveryManager
from src.utils.error_detector import ProactiveErrorDetector
from src.frameworks.detector import FrameworkDetector
from src.frameworks.executors import PlaywrightExecutor, ScrapyExecutor, BrowserUseExecutor  # Added BrowserUseExecutor
from src.validators.script_validator import ScriptValidator
from src.utils.rate_limiter import RateLimiter
# from src.utils.privacy_filter import PrivacyFilter
from src.utils.secure_session import SecureSessionStorage


class WebAutomationAgent:
    def __init__(self):
        self.pool = BrowserPool()
        self.detector = FrameworkDetector()
        self.executor = PlaywrightExecutor()
        self.validator = ScriptValidator()
        self.retry_manager = RetryManager()
        self.recovery_manager = RecoveryManager()
        self.sessions = Path("sessions"); self.sessions.mkdir(exist_ok=True)
        self.scripts = Path("scripts"); self.scripts.mkdir(exist_ok=True)
        self.crawl_delay = 0  # Default crawl delay from robots.txt
        self.rate_limiter = RateLimiter()
        # self.privacy_filter = PrivacyFilter()
        self.secure_sessions = SecureSessionStorage(self.sessions)

    TEMPLATE = Template('''
import asyncio, json, csv, os, aiofiles
from pathlib import Path
from playwright.async_api import async_playwright
import pandas as pd

DATA = Path("data"); DATA.mkdir(exist_ok=True)
SESSIONS = Path("sessions"); SESSIONS.mkdir(exist_ok=True)  # Added: Ensure sessions dir exists
async def save(kind, payload, name):
    out = (DATA / name).with_suffix(f".{kind}")
    if kind == "json":
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, indent=2, ensure_ascii=False))
    elif kind == "csv":
        pd.DataFrame(payload).to_csv(out, index=False)
    else:
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(str(payload))
    print(f"Saved → {out.name}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="{{ ua }}",
            viewport={"width": 1920, "height": 1080}
        )
        session = "{{ session }}"
        if os.path.exists(session):
            await context.storage_state(path=session)
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await page.goto("{{ url }}", wait_until="domcontentloaded")
{% for step in steps %}
        # {{ step.comment }}
        try:
{{ step.code }}
            print("✓ Step {{ loop.index }}")
        except Exception as e:
            print("✗ Step {{ loop.index }}:", e)
            await page.screenshot(path="step_{{ loop.index }}_error.png")
            raise
{% endfor %}
        await context.storage_state(path=session)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
''')

    # ---------- CLARIFIER ---------- #
    async def _clarify(self, html: str) -> str:
        prompt = CLARIFIER.format(task=self.state.task, html=html[:1000])
        reply = await ask_llm("You are helpful.", prompt, temp=0.1)
        if reply.lower() not in ["ok", "yes", "clear"]:
            print(f"❓ {reply}")
            answer = input("Your answer: ").strip()
            self.state.task += f" | Clarification: {answer}"
            return answer
        return ""

    # ---------- PLANNER (ENHANCED) ---------- #
    async def _plan(self, html: str, framework: str) -> list:
        history = json.dumps(self.state.attempt_history[-2:]) if self.state.attempt_history else "None"
        
        # Add framework hints to prompt
        framework_hint = {
            "scrapy": "Use CSS selectors only. No JavaScript execution.",
            "playwright": "Use playwright. Auto-paginate if 'all' mentioned.",
            "browser-use": "Use vision. Click elements by relative position."
        }
        
        prompt = PLANNER.format(
            task=self.state.task,
            frontend=f"{framework} ({framework_hint.get(framework, '')})",
            html=html[:1500],            tech_info=json.dumps(self.state.tech_info, indent=2),            history=history,
            url=self.state.url
        )
        raw = await ask_llm("You are a planner. Return JSON array only.", prompt)
        print(f"Raw LLM output for plan: {raw}")
        raw = raw.strip().removeprefix('```json').removesuffix('```').strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                steps = parsed.get("steps", parsed.get("plan", []))
            else:
                steps = parsed
                
            # Auto-add pagination if task implies multi-page
            #if "all" in self.state.task.lower() and "paginate" not in str(steps):
             #   steps.append({
              #      "comment": "Paginate until no more data",
               #     "action": "paginate",
                #    "save_as": "paginated_data"
                #})
            if "extract" not in str(steps) and ("extract" in self.state.task.lower() or "scrape" in self.state.task.lower()):
                steps.append({
                    "comment": "Extract content",
                    "action": "extract",
                    "selector": "article",
                    "fields": {"title": "h1", "body": "p, h2"},
                    "save_as": "content",
                    "critical": True
                })

            self.state.attempt_history.append({"plan": steps, "framework": framework})
            return steps
        except Exception as e:
            print(f"Bad JSON from LLM – fallback: {e}")
            default_steps = [
                {"comment": "Navigate", "element": "", "action": "goto", "critical": True},
                {"comment": "Extract content", "action": "extract", "selector": "article", "fields": {"title": "h1", "body": "p, h2"}, "save_as": "content", "critical": True}
            ]
            return default_steps

    # ---------- REPLAN WITH FEEDBACK ---------- #
    async def _replan_with_feedback(self, html: str, feedback: str) -> list:
        history = json.dumps(self.state.attempt_history[-2:], indent=2)
        prompt = f"""
Previous attempts:
{history}

User feedback: {feedback}

Current task: {self.state.task}
HTML snapshot: {html[:1200]}

Generate a CORRECTED plan that addresses the feedback.
Return a JSON array of steps only, no outer object.
"""
        raw = await ask_llm("You learn from mistakes. Return JSON only. No markdown or code blocks.", prompt)
        print(f"Raw LLM output for replan: {raw}")
        raw = raw.strip().removeprefix('```json').removesuffix('```').strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "plan" in parsed:
                steps = parsed["plan"]
            else:
                steps = parsed if isinstance(parsed, list) else []
            self.state.attempt_history.append({"feedback": feedback, "new_plan": steps})
            return steps
        except:
            print("Replan failed – using fallback")
            return [{"comment": "Extract", "action": "extract", "save_as": "fallback", "critical": True}]

    # ---------- COMPRESS HTML ---------- #
    async def _compress_html(self, page: Page) -> str:
        await page.wait_for_load_state("domcontentloaded")
        
        # Improved HTML compression: Sample representative elements from different page sections
        # Instead of just first 60 elements, sample from header, main, footer, and other areas
        els = await page.evaluate(
            """() => {
                const selectors = 'a, button, input, select, textarea, form, h1, h2, h3, p, img, [role="button"], [role="link"]';
                const sampleSize = 20; // Sample size per section
                
                // Sample from different page sections for better representation
                const sections = [
                    'header, nav, .header, .nav, #header, #nav',
                    'main, .main, #main, article, .content, #content',
                    'footer, .footer, #footer',
                    'aside, .sidebar, .aside, #sidebar',
                    'body' // Fallback for remaining elements
                ];
                
                const sampledElements = [];
                
                for (const sectionSelector of sections) {
                    try {
                        const sectionElements = Array.from(document.querySelectorAll(`${sectionSelector} ${selectors}`));
                        // Take sample from this section
                        const sectionSample = sectionElements.slice(0, sampleSize);
                        sampledElements.push(...sectionSample);
                        
                        // If we have enough samples, break
                        if (sampledElements.length >= sampleSize * sections.length) break;
                    } catch (e) {
                        // Continue if section selector fails
                        continue;
                    }
                }
                
                // If still not enough, fill with any remaining elements
                if (sampledElements.length < 60) {
                    const allElements = Array.from(document.body.querySelectorAll(selectors));
                    const remaining = allElements.filter(el => !sampledElements.includes(el));
                    sampledElements.push(...remaining.slice(0, 60 - sampledElements.length));
                }
                
                // Limit to 60 total elements but from diverse sections
                return sampledElements.slice(0, 60).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    text: (el.textContent || '').trim().slice(0, 60),
                    id: el.id,
                    placeholder: el.placeholder || '',
                    src: el.src || ''
                }));
            }"""
        )
        return "\n".join(f"<{e['tag']} id='{e['id']}' src='{e['src']}'>{e['text']}</{e['tag']}>" for e in els if e["text"] or e["id"] or e["src"])

    # ---------- VALIDATE API ENDPOINT ---------- #
    async def _validate_api_endpoint(self, endpoint: str, api_info: dict) -> dict:
        """
        Enhanced API endpoint validation with actual data parsing and quality assessment.
        
        Returns dict with validation results and recommendations.
        """
        validation_result = {
            "is_valid": False,
            "recommend_api_mode": False,
            "summary": "",
            "data_quality": 0,
            "response_time": 0,
            "error_details": None
        }
        
        try:
            import aiohttp
            import json
            import time
            
            # Test the API endpoint
            start_time = time.time()
            async with aiohttp.ClientSession() as session:
                headers = api_info.get("headers", {})
                # Add common headers if not present
                if "User-Agent" not in headers:
                    headers["User-Agent"] = "Mozilla/5.0 (compatible; WebScraper/1.0)"
                
                async with session.get(endpoint, headers=headers, timeout=10) as response:
                    response_time = time.time() - start_time
                    validation_result["response_time"] = response_time
                    
                    if response.status != 200:
                        validation_result["error_details"] = f"HTTP {response.status}"
                        validation_result["summary"] = f"API returned HTTP {response.status}"
                        return validation_result
                    
                    content_type = response.headers.get("content-type", "").lower()
                    if "json" not in content_type and "javascript" not in content_type:
                        validation_result["error_details"] = f"Unsupported content type: {content_type}"
                        validation_result["summary"] = f"API returns {content_type}, not JSON"
                        return validation_result
                    
                    # Parse JSON response
                    try:
                        data = await response.json()
                    except Exception as e:
                        validation_result["error_details"] = f"JSON parsing failed: {e}"
                        validation_result["summary"] = "API response is not valid JSON"
                        return validation_result
                    
                    # Analyze data structure and quality
                    quality_score = self._assess_api_data_quality(data)
                    validation_result["data_quality"] = quality_score
                    
                    # Determine if API mode is recommended
                    is_structured = isinstance(data, (list, dict))
                    has_reasonable_size = len(json.dumps(data)) > 100  # At least 100 chars of data
                    fast_response = response_time < 2.0  # Under 2 seconds
                    good_quality = quality_score >= 6  # Out of 10
                    
                    validation_result["is_valid"] = is_structured and has_reasonable_size
                    validation_result["recommend_api_mode"] = (
                        validation_result["is_valid"] and fast_response and good_quality
                    )
                    
                    # Generate summary
                    data_type = "array" if isinstance(data, list) else "object"
                    item_count = len(data) if isinstance(data, list) else "N/A"
                    validation_result["summary"] = (
                        f"Valid {data_type} API (quality: {quality_score}/10, "
                        f"{item_count} items, {response_time:.2f}s response)"
                    )
                    
        except Exception as e:
            validation_result["error_details"] = str(e)
            validation_result["summary"] = f"API validation failed: {e}"
        
        return validation_result
    
    def _assess_api_data_quality(self, data) -> int:
        """
        Assess the quality of API response data on a scale of 1-10.
        
        Considers: structure, field diversity, data completeness, etc.
        """
        score = 0
        
        try:
            if isinstance(data, list):
                if len(data) == 0:
                    return 2  # Empty array
                
                # Check first few items
                sample_items = data[:min(5, len(data))]
                if not all(isinstance(item, dict) for item in sample_items):
                    return 3  # Not all items are objects
                
                # Analyze field consistency and quality
                all_fields = set()
                total_fields = 0
                populated_fields = 0
                
                for item in sample_items:
                    item_fields = set(item.keys())
                    all_fields.update(item_fields)
                    total_fields += len(item_fields)
                    
                    # Count non-empty values
                    for value in item.values():
                        if value is not None and str(value).strip():
                            populated_fields += 1
                
                # Score based on field diversity and completeness
                avg_fields_per_item = total_fields / len(sample_items)
                completeness_ratio = populated_fields / total_fields if total_fields > 0 else 0
                
                # Field diversity (more fields = better)
                if avg_fields_per_item >= 5:
                    score += 3
                elif avg_fields_per_item >= 3:
                    score += 2
                else:
                    score += 1
                
                # Data completeness
                if completeness_ratio >= 0.8:
                    score += 3
                elif completeness_ratio >= 0.5:
                    score += 2
                else:
                    score += 1
                
                # Reasonable data size
                if len(data) >= 10:
                    score += 2
                elif len(data) >= 3:
                    score += 1
                
            elif isinstance(data, dict):
                # Single object response
                fields = list(data.keys())
                populated = sum(1 for v in data.values() if v is not None and str(v).strip())
                
                if len(fields) >= 5:
                    score += 3
                elif len(fields) >= 3:
                    score += 2
                else:
                    score += 1
                
                completeness = populated / len(fields) if fields else 0
                if completeness >= 0.8:
                    score += 3
                elif completeness >= 0.5:
                    score += 2
                else:
                    score += 1
                
                score += 1  # Bonus for being an object
                
            else:
                return 1  # Not list or dict
                
        except Exception:
            return 1  # Error during analysis
        
        return min(10, max(1, score))  # Clamp between 1-10

    # ---------- SAVE LARGE DATASET CHUNK ---------- #
    async def _save_large_dataset_chunk(self, save_as: str, data: list) -> None:
        """Save large datasets to disk immediately to prevent memory accumulation."""
        try:
            import aiofiles
            import json
            from pathlib import Path
            
            # Create data directory if it doesn't exist
            data_dir = Path("data")
            data_dir.mkdir(exist_ok=True)
            
            # Save as JSON with timestamp to avoid overwrites
            timestamp = int(time.time() * 1000)  # millisecond precision
            chunk_file = data_dir / f"{save_as}_chunk_{timestamp}.json"
            
            async with aiofiles.open(chunk_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
            
            logger.info(f"💾 Saved {len(data)} items to {chunk_file}")
            
        except Exception as e:
            logger.error(f"Failed to save large dataset chunk: {e}")
            # Continue execution - don't fail the whole process

    # ---------- LOAD SAVED DATA CHUNKS ---------- #
    async def _load_saved_data_chunks(self, save_as: str) -> list:
        """Load all saved data chunks for a given save_as key."""
        try:
            import aiofiles
            from pathlib import Path
            
            data_dir = Path("data")
            if not data_dir.exists():
                return []
            
            all_data = []
            chunk_pattern = f"{save_as}_chunk_*.json"
            
            for chunk_file in data_dir.glob(chunk_pattern):
                try:
                    async with aiofiles.open(chunk_file, "r", encoding="utf-8") as f:
                        chunk_data = json.loads(await f.read())
                        all_data.extend(chunk_data)
                    
                    # Clean up chunk file after loading
                    chunk_file.unlink()
                    logger.debug(f"🗑️ Cleaned up chunk file: {chunk_file}")
                    
                except Exception as e:
                    logger.warning(f"Failed to load chunk {chunk_file}: {e}")
            
            logger.info(f"📂 Loaded {len(all_data)} items from {len(list(data_dir.glob(chunk_pattern)))} chunks")
            return all_data
            
        except Exception as e:
            logger.error(f"Failed to load saved data chunks: {e}")
            return []

    # ---------- PROCESS DATA IN CHUNKS ---------- #
    async def _process_data_in_chunks(self, data: list, chunk_size: int = 500) -> None:
        """Process large datasets in chunks to prevent memory issues."""
        if len(data) <= chunk_size:
            return  # No need to chunk small datasets
        
        logger.info(f"🔄 Processing {len(data)} items in chunks of {chunk_size}")
        
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]
            # Process chunk (could add validation, filtering, etc. here)
            logger.debug(f"📦 Processed chunk {i//chunk_size + 1}/{(len(data) + chunk_size - 1)//chunk_size}")
            
            # Force garbage collection hint for large chunks
            if len(chunk) > 1000:
                import gc
                gc.collect()
        
        logger.info(f"✅ Completed chunked processing of {len(data)} items")

    # ---------- EXECUTE STEP WITH POST-PROCESSING ---------- #
    async def _execute_step_with_postprocessing(self, page: Page, step: dict) -> None:
        """Execute a step with built-in post-processing and validation."""
        # Respect crawl delay from robots.txt
        if self.crawl_delay > 0:
            logger.debug(f"⏱️ Applying crawl delay: {self.crawl_delay}s")
            await asyncio.sleep(self.crawl_delay)

        # Execute the step
        await self.executor.execute_step(page, step, self.state.tech_info)

        # Post-processing based on step type
        if step["action"] == "extract":
            extracted_data = step.get("extracted_data", [])

            # Basic data validation
            if isinstance(extracted_data, list) and len(extracted_data) > 0:
                # Remove empty entries
                filtered_data = [item for item in extracted_data if any(str(val).strip() for val in item.values())]
                
                # Process large datasets in chunks to prevent memory issues
                if len(filtered_data) > 1000:  # Very large dataset threshold
                    await self._process_data_in_chunks(filtered_data)
                
                step["extracted_data"] = filtered_data

                # Memory management: Save large datasets immediately to disk
                if len(filtered_data) > 100:  # Threshold for large datasets
                    await self._save_large_dataset_chunk(step["save_as"], filtered_data)
                    # Clear from memory after saving
                    step["extracted_data"] = []
                    step["data_saved_to_disk"] = True
                    logger.info(f"💾 Large dataset ({len(filtered_data)} items) saved to disk for {step['save_as']}")

                # Log extraction summary
                logger.info(f"📊 Extracted {len(filtered_data)} valid items")

                # Quality check - warn if too few items extracted
                if len(filtered_data) < 1:
                    logger.warning("⚠️ Very few items extracted - selector might be too specific")

            elif extracted_data is None:
                step["extracted_data"] = []
                logger.warning("⚠️ No data extracted")

        elif step["action"] == "click":
            # Brief pause after clicks to let page settle
            await asyncio.sleep(0.5)

        elif step["action"] == "fill":
            # Verify input was filled (basic check)
            if step.get("verify_fill", False):
                selector = step.get("selector") or f"text={step.get('element', '')}"
                try:
                    value = await page.locator(selector).input_value()
                    if not value:
                        logger.warning(f"⚠️ Input field may not have been filled: {selector}")
                except Exception as e:
                    logger.debug(f"Could not verify input fill: {e}")

    # ---------- ROBOTS.TXT CHECK ---------- #
    async def check_robots(self, url: str, page: Page) -> bool:
        """
        Properly check robots.txt using robotparser.
        Respects Crawl-delay directives and checks specific disallow rules.
        """
        try:
            parsed_url = urlparse(url)
            robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"

            # Create robot parser
            rp = robotparser.RobotFileParser()
            rp.set_url(robots_url)

            # Read and parse robots.txt
            try:
                rp.read()
                logger.info(f"📋 Parsed robots.txt from {robots_url}")
            except Exception as e:
                logger.warning(f"⚠️ Could not read robots.txt: {e}")
                # If we can't read robots.txt, assume we're allowed (be conservative)
                return True

            # Check if we're allowed to access the main URL
            if not rp.can_fetch("*", url):
                logger.warning(f"🚫 robots.txt disallows access to: {url}")
                return False

            # Check crawl delay
            crawl_delay = rp.crawl_delay("*")
            if crawl_delay:
                logger.info(f"⏱️ Respecting crawl delay: {crawl_delay} seconds")
                # Store crawl delay for use in execution
                self.crawl_delay = crawl_delay
                # Set rate limiter delay for this domain
                domain = urlparse(url).netloc
                self.rate_limiter.set_domain_delay(domain, crawl_delay)

            # Check specific paths we might access
            paths_to_check = [
                "/",  # Root
                "/search",  # Common search endpoints
                "/api",  # API endpoints
                parsed_url.path,  # The specific path we're targeting
            ]

            # Remove duplicates and empty paths
            paths_to_check = list(set(path for path in paths_to_check if path))

            disallowed_paths = []
            for path in paths_to_check:
                full_url = urljoin(url, path)
                if not rp.can_fetch("*", full_url):
                    disallowed_paths.append(path)

            if disallowed_paths:
                logger.warning(f"🚫 robots.txt disallows access to paths: {disallowed_paths}")
                return False

            logger.info("✅ robots.txt check passed")
            return True

        except Exception as e:
            logger.error(f"❌ Error checking robots.txt: {e}")
            # On error, be conservative and allow access
            return True

    # ---------- MAIN RUN ---------- #
    async def run(self, max_attempts: int = 5):
        self.state = AgentState(url=os.getenv("TARGET_URL"), task=os.getenv("TASK_DESCRIPTION"))
        if not self.state.url or not self.state.task:
            raise ValueError("TARGET_URL and TASK_DESCRIPTION must be in .env")

        print(f"🚀 Task: {self.state.task}")
        print(f"📍 URL: {self.state.url}")
        print(f"🔁 Max attempts: {max_attempts}")

        for attempt in range(max_attempts):
            print(f"\n{'='*60}\n Attempt #{attempt + 1}\n{'='*60}")

            browser = await self.pool.get()
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            domain = self.state.url.split("//")[-1].split("/")[0]
            session_data = self.secure_sessions.load_session(domain)
            if session_data:
                # Create a temporary file for Playwright to load
                import tempfile
                import json
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                    json.dump(session_data, temp_file)
                    temp_file_path = temp_file.name
                
                try:
                    await context.storage_state(path=temp_file_path)
                    logger.info(f"🔐 Loaded secure session for {domain}")
                finally:
                    # Clean up temp file
                    import os
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass
            page = await context.new_page()

            # 1. Navigate & check robots.txt
            # Apply rate limiting before navigation
            await self.rate_limiter.wait_if_needed(self.state.url)
            
            await page.goto(self.state.url, wait_until="domcontentloaded")
            # Wait for content to load
            await page.wait_for_timeout(2000)  # Give time for dynamic content
            if not await self.check_robots(self.state.url, page):
                await self.pool.release(browser)
                return  # Abort if disallowed

            html = await self._compress_html(page)
            try:
                self.state.framework = await self.detector.detect(page, len(html))
                self.state.tech_info = await self.detector._analyze_tech_stack(page)  # Store detailed tech info
            except Exception as e:
                logger.warning(f"Framework detection failed, using default playwright: {e}")
                self.state.framework = "playwright"
                self.state.tech_info = {}

            # 1.5. Proactive error detection
            try:
                warnings = await ProactiveErrorDetector.detect_impending_errors(page, self.state.tech_info)
                if warnings:
                    logger.warning(f"⚠️ Detected potential issues: {warnings}")

                    # Get prevention recommendations
                    recommendations = await ProactiveErrorDetector.get_prevention_recommendations(warnings)

                    # Check if we should proceed
                    if not ProactiveErrorDetector.should_proceed_with_scraping(warnings):
                        logger.error(f"🚫 Critical issues detected, aborting scraping: {warnings}")
                        await self.pool.release(browser)
                        return

                    # Apply prevention measures
                    if recommendations.get("use_proxy"):
                        logger.info("🔄 Enabling proxy rotation due to detected issues")
                        # Note: Actual proxy implementation would go here

                    if recommendations.get("add_delays"):
                        logger.info("⏱️ Adding extra delays due to detected issues")
                        await page.wait_for_timeout(3000)  # Extra 3 second delay

                    if recommendations.get("stealth_mode"):
                        logger.info("🕵️ Enabling stealth mode due to bot detection")
                        # Note: Additional stealth measures would go here

            except Exception as e:
                logger.debug(f"Proactive error detection failed: {e}")
                # Continue anyway - detection failure shouldn't stop scraping

            # 2. Try API-First mode if Playwright detected
            if self.state.framework == "playwright":
                apis = await APIInterceptor.intercept_api_calls(page)
                if apis and len(apis) > 0:
                    print(f"🔌 Detected API endpoints: {list(apis.keys())}")
                    self.state.api_endpoints = list(apis.keys())  # Store for recovery use
                    endpoint = list(apis.keys())[0]
                    
                    # Enhanced API validation with actual data parsing
                    api_validation_result = await self._validate_api_endpoint(endpoint, apis[endpoint])
                    
                    if api_validation_result["is_valid"]:
                        print(f"✅ API validation successful: {api_validation_result['summary']}")
                        if api_validation_result["recommend_api_mode"]:
                            print("✅ Auto-enabling API-first mode (high-quality API data detected)")
                            self.state.framework = "api-first"
                            script_dir = self.scripts / f"{int(time.time())}_{domain}_{attempt}_api"
                            script_dir.mkdir(parents=True, exist_ok=True)
                            
                            # Generate enhanced script with validation
                            from utils.api_interceptor import generate_requests_script
                            script = generate_requests_script(endpoint, validation_info=api_validation_result)
                            (script_dir / "main.py").write_text(script)
                            print("✅ API-first script generated with enhanced validation")
                            await self.pool.release(browser)
                            break
                    
                    # Fallback to manual decision if auto-detection inconclusive
                    print(f"🤔 API detected but validation inconclusive: {api_validation_result['summary']}")
                    use_api = input("Use API-first mode? (yes/no): ").strip().lower()
                    if use_api in ["yes", "y"]:
                        self.state.framework = "api-first"
                        # Generate and save script as above
                        await self.pool.release(browser)
                        break

            # 3. Clarify & Plan
            await self._clarify(html)
            steps = await self._plan(html, self.state.framework)
            print("📋 Plan:", json.dumps(steps, indent=2))

            # 4. Execute (framework-aware)
            extracted_data = {}
            browser = None
            try:
                if self.state.framework == "browser-use":
                    extracted_data = await BrowserUseExecutor.execute_steps(self.state.url, self.state.task, steps)
                else:
                    browser = await self.pool.get()
                    page = await browser.new_page()
                    
                    # Set reasonable timeouts and resource limits
                    page.set_default_timeout(30000)  # 30 seconds
                    page.set_default_navigation_timeout(30000)
                    
                    for idx, step in enumerate(steps, 1):
                        step_name = f"Step {idx}: {step['comment']}"
                        print(f"Executing {step_name}")
                        print(f"Step details: {json.dumps(step, indent=2)}")

                        # Enhanced error handling with recovery
                        recovery_attempted = False

                        try:
                            await self.retry_manager.execute_with_retry(
                                step_func=lambda: self._execute_step_with_postprocessing(page, step),
                                step_name=step_name,
                                max_retries=2,  # Reduced from 6, let recovery handle more
                                context={"tech_info": self.state.tech_info, "step_idx": idx}
                            )

                            # Success - handle data extraction
                            if step["action"] == "extract":
                                if step.get("data_saved_to_disk", False):
                                    # Data was saved to disk, load it later
                                    extracted_data[step["save_as"]] = f"STREAMED_TO_DISK"
                                    print(f"Data streamed to disk for {step['save_as']}")
                                else:
                                    # Data kept in memory
                                    extracted_data[step["save_as"]] = step.get("extracted_data", [])
                                    print(f"Extracted data sample: {json.dumps(extracted_data[step['save_as']][:2], indent=2)}")
                            elif step["action"] == "download":
                                urls = await page.evaluate(
                                    f"""() => Array.from(document.querySelectorAll('{step.get("selector", "img")}'))
                                              .map(el => el.src || el.href).filter(u => u)"""
                                )
                                await save(step.get("format", "png"), urls, step["save_as"])

                        except Exception as e:
                            error_type = ErrorClassifier.classify_error(e)
                            severity = ErrorClassifier.get_error_severity(error_type)

                            if severity == "critical":
                                logger.error(f"🚨 Critical error in {step_name}: {error_type} - {str(e)}")
                                raise  # Don't continue with critical errors

                            # Attempt recovery if not already tried
                            if not recovery_attempted and RecoveryManager.should_attempt_recovery(error_type, 1):
                                logger.warning(f"🔧 Attempting recovery for {step_name} ({error_type})")
                                recovery_step = self.recovery_manager.get_fallback_strategy(
                                    error_type, step, {
                                        "tech_info": self.state.tech_info,
                                        "api_endpoints": self.state.api_endpoints,
                                        "spa": self.state.tech_info.get("spa", False),
                                        "page_url": self.state.url
                                    }
                                )

                                try:
                                    await self.retry_manager.execute_with_retry(
                                        step_func=lambda: self._execute_step_with_postprocessing(page, recovery_step),
                                        step_name=f"{step_name} (recovery)",
                                        max_retries=1,
                                        context={"tech_info": self.state.tech_info, "recovery": True}
                                    )

                                    # Recovery successful
                                    if recovery_step["action"] == "extract":
                                        if recovery_step.get("data_saved_to_disk", False):
                                            extracted_data[recovery_step["save_as"]] = f"STREAMED_TO_DISK"
                                        else:
                                            extracted_data[recovery_step["save_as"]] = recovery_step.get("extracted_data", [])
                                        print(f"✅ Recovery successful - extracted data sample: {json.dumps(extracted_data[recovery_step['save_as']][:2], indent=2)}")

                                    recovery_attempted = True
                                    logger.success(f"🔧 Recovery successful for {step_name}")

                                except Exception as recovery_error:
                                    logger.error(f"❌ Recovery failed for {step_name}: {str(recovery_error)}")
                                    
                                    # Check if this step is critical - critical steps should fail the entire process
                                    if step.get("critical", False):
                                        logger.error(f"🚨 Critical step {step_name} failed recovery - aborting process")
                                        raise Exception(f"Critical step failed: {step_name} - {str(recovery_error)}")
                                    else:
                                        logger.warning(f"⚠️ Skipping non-critical failed step: {step_name} ({error_type})")
                                        # Continue to next step instead of failing completely

                            else:
                                # No recovery attempted or not applicable
                                if step.get("critical", False):
                                    logger.error(f"🚨 Critical step {step_name} failed with no recovery option - aborting process")
                                    raise Exception(f"Critical step failed: {step_name} - {str(e)}")
                                else:
                                    logger.warning(f"⚠️ Skipping failed step: {step_name} ({error_type})")
                                    # Continue to next step instead of failing the entire process

            finally:
                # Explicit browser cleanup in finally block
                if browser:
                    try:
                        # Close all pages in the browser context
                        pages = browser.contexts[0].pages if browser.contexts else []
                        for page in pages:
                            try:
                                await page.close()
                            except Exception:
                                pass  # Ignore errors during cleanup
                        
                        # Release browser back to pool
                        await self.pool.release(browser)
                        logger.debug("🧹 Browser context cleaned up successfully")
                    except Exception as cleanup_error:
                        logger.warning(f"Browser cleanup warning: {cleanup_error}")
                        # Don't re-raise cleanup errors

            # 5. Generate script (framework-aware)
            script_dir = self.scripts / f"{int(time.time())}_{domain}_{attempt}"
            script_dir.mkdir(parents=True, exist_ok=True) 
            if self.state.framework == "scrapy":
                extract_step = next((s for s in steps if s.get("action") == "extract"), {})
                script = ScrapyExecutor.generate_spider(
                    self.state.url,
                    self.state.task,
                    step=extract_step
                )
                script_path = script_dir / "spider.py"
                script_path.write_text(script)
            elif self.state.framework == "browser-use":
                script = BrowserUseExecutor.generate_code(self.state.url, self.state.task, steps)
                script_path = script_dir / "main.py"
                script_path.write_text(script)
            else:
                script_steps = [{"comment": s["comment"], "code": self.executor.generate_code(s)} for s in steps]
                script = self.TEMPLATE.render(
                    framework=self.state.framework,
                    url=self.state.url,
                    ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    session=str(session_file),
                    steps=script_steps
                )
                script_path = script_dir / "main.py"
                script_path.write_text(script)
                (script_dir / "data_sample.json").write_text(json.dumps(extracted_data, indent=2))
            print(f"📁 Script saved → {script_path}")
            print(f"📁 Data saved → {script_dir / 'data_sample.json'}")

            # 6. Validate & Test
            valid, error = self.validator.check_syntax(script_path)
            if not valid:
                print(f"⚠️  Syntax error: {error}")
                if attempt < max_attempts - 1:
                    steps = await self._replan_with_feedback(html, f"Syntax error: {error}")
                    await self.pool.release(browser)
                    continue

            # Apply privacy filtering to extracted data
            # for key, data in extracted_data.items():
            #     if isinstance(data, (list, dict)):
            #         # Scan for PII first
            #         pii_types = self.privacy_filter.scan_for_pii(data)
            #         if pii_types:
            #             logger.warning(f"🔒 PII detected in {key}: {pii_types}")
            #         
            #         # Apply privacy filtering
            #         extracted_data[key] = self.privacy_filter.filter_data(data, redact=True)
            #         logger.info(f"🔒 Applied privacy filtering to {key}")

            # Save session securely after successful completion
            try:
                session_data = await context.storage_state()
                domain = self.state.url.split("//")[-1].split("/")[0]
                self.secure_sessions.save_session(domain, session_data)
                logger.info(f"🔐 Session saved securely for {domain}")
            except Exception as e:
                logger.warning(f"Failed to save session: {e}")
            
            if any("csv" in s.get("save_as", "") for s in steps):
                from content_saver import save
                csv_path = await save("csv", extracted_data.get("data", []), "exported")
                print(f"📁 CSV exported → {csv_path}")

            # 8. Human approval
            approved, feedback = await self._ask_approval(extracted_data, script_path)
            if approved:
                await self.pool.release(browser)
                print("✅ Task completed successfully!")
                break
            else:
                print(f"❌ Feedback: {feedback}")
                if attempt < max_attempts - 1:
                    steps = await self._replan_with_feedback(html, feedback)
                    await self.pool.release(browser)
                    print("🔄 Re-planning...")
                else:
                    print("Max attempts reached. Saving final version.")

        tk.print_summary(self.state.start)
        await self.pool.close()

    # ---------- ASK APPROVAL ---------- #
    async def _ask_approval(self, data_sample: dict, script_path: Path) -> tuple[bool, str]:
        print("\n" + "="*60)
        print("🎯 Agent has completed the task!")
        print(f"📦 Data files: {list(data_sample.keys())}")
        print(f"📝 Sample (first 3 items):\n{json.dumps(data_sample, indent=2)[:500]}...")
        print("="*60)
        
        approve = input("✅ Approve & finish? (yes/no): ").strip().lower()
        if approve in ["yes", "y"]:
            return True, ""
        
        feedback = input("❌ What went wrong? (e.g., wrong data, missing fields): (").strip()
        return False, feedback


# ---------- ENTRY ---------- #
if __name__ == "__main__":
    asyncio.run(WebAutomationAgent().run())
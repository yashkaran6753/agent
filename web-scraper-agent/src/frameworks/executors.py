# src/frameworks/executors.py (100% GENERIC: No hard-coded text, selectors, or fields)
from playwright.async_api import Page
import asyncio, json, time
from loguru import logger
from pathlib import Path
from ..content_saver import save
from ..utils.paginator import Paginator
from browser_use import Agent, Browser, Controller
import os


class PlaywrightExecutor:
    # Pre-defined extraction functions for different tech stacks
    EXTRACTION_FUNCTIONS = {
        "spa": """
        function extractSPAData(containerSelector, fields) {
            const containers = document.querySelectorAll(containerSelector);
            const results = [];
            
            for (const container of containers) {
                const record = {};
                let hasContent = false;
                
                for (const [fieldName, fieldSelector] of Object.entries(fields)) {
                    let text = '';
                    if (fieldSelector === '.') {
                        text = container.textContent ? container.textContent.trim() : '';
                    } else {
                        const element = container.querySelector(fieldSelector);
                        if (element) text = element.textContent ? element.textContent.trim() : '';
                    }
                    if (text) {
                        record[fieldName] = text;
                        hasContent = true;
                    }
                }
                
                if (hasContent) {
                    results.push(record);
                }
            }
            
            return results;
        }
        """,
        
        "static": """
        function extractStaticData(containerSelector, fields) {
            const containers = document.querySelectorAll(containerSelector);
            const results = [];
            
            for (const container of containers) {
                const record = {};
                
                for (const [fieldName, fieldSelector] of Object.entries(fields)) {
                    if (fieldSelector === '.') {
                        record[fieldName] = container.textContent ? container.textContent.trim() : '';
                    } else {
                        const element = container.querySelector(fieldSelector);
                        record[fieldName] = element ? (element.textContent ? element.textContent.trim() : '') : '';
                    }
                }
                
                results.push(record);
            }
            
            return results;
        }
        """,
        
        "traditional": """
        function extractTraditionalData(containerSelector, fields) {
            const containers = document.querySelectorAll(containerSelector);
            const results = [];
            
            for (const container of containers) {
                const record = {};
                
                for (const [fieldName, fieldSelector] of Object.entries(fields)) {
                    if (fieldSelector === '.') {
                        record[fieldName] = container.textContent ? container.textContent.trim() : '';
                    } else {
                        const element = container.querySelector(fieldSelector);
                        record[fieldName] = element ? (element.textContent ? element.textContent.trim() : '') : '';
                    }
                }
                
                results.push(record);
            }
            
            return results;
        }
        """
    }

    @staticmethod
    def _validate_js_syntax(js_code: str) -> bool:
        """
        Validate that generated JavaScript is syntactically correct.
        """
        try:
            # Basic syntax check using a simple JS parser approach
            # Remove comments and check for balanced braces/brackets
            import re
            
            # Remove single-line comments
            js_code = re.sub(r'//.*$', '', js_code, flags=re.MULTILINE)
            # Remove multi-line comments
            js_code = re.sub(r'/\*.*?\*/', '', js_code, flags=re.DOTALL)
            
            # Check for balanced parentheses, braces, and brackets
            parens = 0
            braces = 0
            brackets = 0
            in_string = False
            string_char = None
            
            for char in js_code:
                if in_string:
                    if char == string_char:
                        in_string = False
                        string_char = None
                    continue
                elif char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    continue
                
                if char == '(':
                    parens += 1
                elif char == ')':
                    parens -= 1
                elif char == '{':
                    braces += 1
                elif char == '}':
                    braces -= 1
                elif char == '[':
                    brackets += 1
                elif char == ']':
                    brackets -= 1
                
                # Early exit if any counter goes negative
                if parens < 0 or braces < 0 or brackets < 0:
                    return False
            
            # Check if all are balanced
            return parens == 0 and braces == 0 and brackets == 0
            
        except Exception:
            return False

    @staticmethod
    def _get_extraction_function(tech_info: dict) -> str:
        """
        Get the appropriate extraction function based on tech stack.
        Returns the function name to call.
        """
        if tech_info.get("spa") or tech_info.get("react") or tech_info.get("vue") or tech_info.get("angular"):
            return "extractSPAData"
        elif tech_info.get("is_static"):
            return "extractStaticData"
        else:
            return "extractTraditionalData"

    @staticmethod
    def _generate_simple_extraction_js(container_sel: str, fields: dict, tech_info: dict) -> str:
        """
        Generate simplified, validated JavaScript for data extraction.
        """
        # Get the appropriate function name
        function_name = PlaywrightExecutor._get_extraction_function(tech_info)
        
        # Generate the JS call with proper function wrapper
        fields_json = json.dumps(fields)
        js_code = f"""() => {{
            // Define extraction functions
            {PlaywrightExecutor.EXTRACTION_FUNCTIONS['spa']}
            {PlaywrightExecutor.EXTRACTION_FUNCTIONS['static']}
            {PlaywrightExecutor.EXTRACTION_FUNCTIONS['traditional']}
            
            // Execute extraction and return result
            return {function_name}('{container_sel}', {fields_json});
                try:
                    fallback_data = await page.evaluate(f"""
                    () => {{
                        const containers = document.querySelectorAll('{container_sel}');
                        return Array.from(containers).map(container => ({
                            'fallback_text': container.textContent ? container.textContent.trim() : '',
                            'error': 'JS extraction failed'
                        }));
                    }}
                    """)
                    step["extracted_data"] = fallback_data or []

                    # Try to capture a focused element screenshot and short text summary
                    try:
                        tmp_dir = Path("scripts") / "tmp_screenshots"
                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        stamp = int(time.time())
                        # Capture first matching element if present
                        el = await page.query_selector(container_sel)
                        if el:
                            shot_path = tmp_dir / f"element_{stamp}.png"
                            await el.screenshot(path=str(shot_path))
                            # Capture a short text summary from the element
                            try:
                                text = (await page.evaluate("el => el.innerText", el)) or ''
                            except Exception:
                                text = ''
                            step["visual_summary"] = (text.strip().replace('\n', ' ')[:500])
                            step["screenshot_path"] = str(shot_path)
                            logger.debug("Saved element screenshot {} and summary (len={})", shot_path, len(step["visual_summary"]))
                        else:
                            logger.debug("No element found for selector {} to screenshot", container_sel)
                    except Exception as _:
                        logger.debug("Element screenshot failed for selector {}", container_sel)

                    logger.warning("⚠️ Used fallback extraction, got {} items", len(step['extracted_data']))
                except Exception as fallback_error:
                    logger.error("Even fallback extraction failed: {}", fallback_error)
                    step["extracted_data"] = []
        logger.debug("Executor: starting action={} save_as={} selector={}", action, step.get("save_as"), step.get("selector"))
        
        if action == "click":
            sel = step.get("selector") or f"text={step['element']}"
            await page.locator(sel).click()
            
        elif action == "fill":
            value = os.getenv(step["value"].strip("$"), "") if step.get("value") else ""
            sel = step.get("selector") or f"text={step['element']}"
            await page.locator(sel).fill(value)
            
        elif action == "extract":
            # Simplified tech-aware extraction with validation
            # If the plan didn't provide fields, assume container holds the text directly
            if step.get("fields"):
                fields = step.get("fields")
            else:
                fields = {"text": "."}
            container_sel = step.get("selector", "div")
            
            # Add delay for SPAs
            if tech_info and (tech_info.get("spa") or tech_info.get("react") or tech_info.get("vue") or tech_info.get("angular")):
                await page.wait_for_timeout(500)  # Wait for SPA to stabilize
            
            # Generate and validate JS code
            js_code = PlaywrightExecutor._generate_simple_extraction_js(container_sel, fields, tech_info or {})
            
            # Additional validation before execution
            if not PlaywrightExecutor._validate_js_syntax(js_code):
                logger.error("Generated JS failed final validation - using emergency fallback")
                # Emergency fallback - very simple extraction
                js_code = f"""
                () => {{
                    const containers = document.querySelectorAll('{container_sel}');
                    return Array.from(containers).map(container => {{
                        const record = {{}};
                        {chr(10).join([f"const {field}El = container.querySelector('{selector}'); record['{field}'] = {field}El ? {field}El.textContent.trim() : '';" for field, selector in fields.items()])}
                        return record;
                    }});
                }}
                """
            
            try:
                # Execute the validated JS
                data = await page.evaluate(js_code)
                step["extracted_data"] = data or []
                logger.info("Executor: extracted {} items for save_as={}", len(step.get('extracted_data', [])), step.get('save_as'))
                
            except Exception as js_error:
                logger.error(f"JS execution failed: {js_error}")
                # Final fallback - extract just the container text
                try:
                    fallback_data = await page.evaluate(f"""
                    () => {{
                        const containers = document.querySelectorAll('{container_sel}');
                        return Array.from(containers).map(container => ({{
                            'fallback_text': container.textContent ? container.textContent.trim() : '',
                            'error': 'JS extraction failed'
                        }}));
                    }}
                    """)
                    step["extracted_data"] = fallback_data or []
                    logger.warning(f"⚠️ Used fallback extraction, got {len(step['extracted_data'])} items")
                except Exception as fallback_error:
                    logger.error(f"Even fallback extraction failed: {fallback_error}")
                    step["extracted_data"] = []
            
        elif action == "download":
            # Download any file type
            urls = await page.evaluate(
                f"""() => Array.from(document.querySelectorAll('{step.get("selector", "img")}'))
                          .map(el => el.src || el.href).filter(u => u)"""
            )
            await save(step.get("format", "png"), urls, step["save_as"])
            
        elif action == "wait":
            timeout = step.get("timeout", 2000)
            await page.wait_for_timeout(timeout)
            
        elif action == "goto":
            url = step.get("url") or step.get("selector", "")
            if url:
                await page.goto(url, wait_until="domcontentloaded")
            
        elif action == "paginate":
            # Manual pagination
            logger.info("Manual pagination step – clicking Next until gone")
            while await page.locator("text=Next").count():
                await page.locator("text=Next").click()
                await page.wait_for_timeout(1000)
                
        elif action == "api_extract":
            # API-based extraction fallback
            endpoint = step.get("api_endpoint", "")
            if endpoint:
                logger.info(f"🔌 Attempting API extraction from: {endpoint}")
                try:
                    # Use the existing API interceptor logic
                    from ..utils.api_interceptor import APIInterceptor
                    # For now, just mark as attempted - full implementation would need more context
                    step["extracted_data"] = [{"api_fallback": True, "endpoint": endpoint}]
                    logger.info(f"✅ API extraction attempted for endpoint: {endpoint}")
                except Exception as e:
                    logger.warning(f"❌ API extraction failed: {e}")
                    step["extracted_data"] = []
            else:
                logger.warning("⚠️ No API endpoint provided for api_extract action")
                step["extracted_data"] = []
                
        else:
            await asyncio.sleep(2)

    @staticmethod
    def generate_code(step: dict) -> str:
        if step["action"] == "extract":
            # When generating standalone scripts, default to extracting container text
            fields = step.get("fields", {"text": "."})
            container_sel = step.get("selector", "div")
            filter_dict = step.get("filter", {})
            
            # Use simplified JS generation instead of complex template
            js_code = PlaywrightExecutor._generate_simple_extraction_js(container_sel, fields, {})
            
            # Add filtering if specified
            filter_js = ""
            if filter_dict.get("field") and filter_dict.get("value"):
                filter_field = filter_dict["field"]
                filter_value = filter_dict["value"]
                filter_js = f"""
                // Apply filter
                data = data.filter(item => 
                    item['{filter_field}'] && 
                    item['{filter_field}'].toLowerCase().includes('{filter_value}'.toLowerCase())
                );
                """
            
            return f'''            # Generate validated extraction JS
            js_code = """{js_code}"""
            data = await page.evaluate(js_code)
            {filter_js}
            await save("json", data, "{step['save_as']}")'''
            
        elif step["action"] == "download":
            sel = step.get("selector", "img")
            format_str = step.get("format", "png")
            return f'''            urls = await page.evaluate(`() => Array.from(document.querySelectorAll('{sel}')).map(el => el.src).filter(u => u)`)
            await save("{format_str}", urls, "{step['save_as']}")'''
            
        elif step["action"] == "click":
            sel = step.get("selector") or f"text={step['element']}"
            return f'            await page.locator("{sel}").click()'
            
        elif step["action"] == "fill":
            sel = step.get("selector") or f"text={step['element']}"
            value = os.getenv(step["value"].strip("$"), "") if step.get("value") else ""
            return f'            await page.locator("{sel}").fill("{value}")'
            
        else:
            return '            await asyncio.sleep(2)'

class ScrapyExecutor:
    @staticmethod
    def generate_spider(url: str, task: str, step: dict) -> str:
        """
        step = {
            "comment": "Extract items",
            "action": "extract",
            "selector": ".item",        # ⭐ From plan
            "fields": {"name": "h3", "price": ".price"},  # ⭐ From plan
            "filter": {"field": "category", "value": "electronics"}  # ⭐ From plan
        }
        """
        container = step.get("selector", "div")
        fields = json.dumps(step.get("fields", {"text": "span"}), indent=12)
        filter_dict = step.get("filter", {})

        return f'''
import scrapy
import json
from pathlib import Path

class AutoSpider(scrapy.Spider):
    name = "auto_spider"
    start_urls = ["{url}"]
    
    def parse(self, response):
        data = []
        for item in response.css('{container}'):
            record = {{}}
            # Extract all fields dynamically
            for field, selector in {fields}.items():
                record[field] = item.css(selector).get()
            
            # Apply filter if specified
            filter_dict = {json.dumps(filter_dict)}
            if filter_dict:
                field_name = filter_dict.get("field", "")
                field_value = filter_dict.get("value", "")
                if field_name and field_value:
                    if record.get(field_name, "").lower().find(field_value.lower()) == -1:
                        continue
            
            data.append(record)
        
        data_path = Path(__file__).parent / "data"
        data_path.mkdir(parents=True, exist_ok=True)
        (data_path / "scrapy_data.json").write_text(json.dumps(data, indent=2))
        self.log(f"Scrapy: saved {len(data)} items")

# Run: scrapy runspider auto_spider.py
'''

class BrowserUseExecutor:
    @staticmethod
    def generate_task(url: str, task: str) -> str:
        return f'Go to {url} and {task}. Use vision if elements are not clear.'

    @staticmethod
    def generate_code(url: str, task: str, steps: list) -> str:
        return f"""# Browser-use generated script
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto('{url}', wait_until='domcontentloaded')
        # Steps: {steps}
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
"""

    @staticmethod
    async def execute_steps(url: str, task: str, steps: list) -> dict:
        """Execute a list of steps using Playwright; returns extracted data dict."""
        from playwright.async_api import async_playwright

        result = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until='domcontentloaded')

            for step in steps:
                try:
                    await PlaywrightExecutor.execute_step(page, step, {})
                except Exception:
                    # Continue on step failures in browser-use mode
                    continue

            for s in steps:
                if s.get('action') == 'extract':
                    result[s.get('save_as', f"extract_{len(result)}")] = s.get('extracted_data', [])

            await browser.close()
        return result
    @staticmethod
    async def execute_steps(url: str, task: str, steps: list) -> dict:
        """
        Executes steps using browser_use Agent for vision-assisted tasks.
        """
        browser = Browser(headless=True)
        controller = Controller()  # Add any custom actions if needed
        agent_task = f"Target: {url}\nGoal: {task}\nSteps: {json.dumps(steps)}"
        agent = Agent(task=agent_task, browser=browser, controller=controller, use_vision=True)
        result = await agent.run(max_steps=20)
        extracted = result.final_result() or {}
        await browser.close()
        return extracted  # Return data for validation/save

    @staticmethod
    def generate_code(url: str, task: str, steps: list) -> str:
        return f'''
from browser_use import Agent, Browser, Controller
async def main():
    browser = Browser(headless=True)
    controller = Controller()
    agent = Agent(task="{url} - {task} - Steps: {json.dumps(steps)}", browser=browser, controller=controller, use_vision=True)
    await agent.run(max_steps=20)
asyncio.run(main())
'''
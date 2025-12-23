# test_planning_flow.py (CORRECTED)
# python test_planning_flow.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
import asyncio
import json
from playwright.async_api import async_playwright
from src.frameworks.detector import FrameworkDetector
from src.prompts.planner import PLANNER
from src.frameworks.executors import PlaywrightExecutor

async def test_planning_flow(url: str, task: str):
    """Test the complete planning and execution flow."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print(f"\n🌐 Testing: {url}")
        print(f"📝 Task: {task}")

        # Step 1: Navigate FIRST
        print("1. Navigating to page...")
        await page.goto(url, wait_until="networkidle")
        
        # Step 2: Detect tech stack
        print("2. Detecting tech stack...")
        tech_info = await FrameworkDetector._analyze_tech_stack(page)
        summary = FrameworkDetector._format_tech_summary(tech_info)
        print(f"   Tech: {summary}")
        
        # Step 2: Get HTML snapshot
        #await page.goto(url, wait_until="networkidle")
        html_content = await page.content()
        html_snapshot = html_content[:5000]  # First 5000 chars
        
        # Step 3: Generate plan (simulate LLM call)
        print("2. Generating plan...")
        prompt = PLANNER.format(
            frontend="playwright",
            task=task,
            html=html_snapshot,
            tech_info=json.dumps(tech_info, indent=2),
            history="[]",
            url=url
        )
        
        # Simulated LLM response
        simple_plan = [
            {
                "comment": "Navigate to target page",
                "action": "goto",
                "url": url
            },
            {
                "comment": "Wait for initial content",
                "action": "wait",
                "timeout": 2000
            },
            {
                "comment": "Extract main content",
                "action": "extract",
                "selector": "article, main, .content, [role='main']",
                "fields": {
                    "title": "h1, .title, .headline",
                    "content": "p, .text, .content"
                },
                "save_as": "extracted_content"
            }
        ]
        
        print(f"   Plan: {len(simple_plan)} steps")
        
        # Step 4: Execute plan WITH TECH INFO
        print("3. Executing plan...")
        extracted_data = None
        for i, step in enumerate(simple_plan, 1):
            print(f"   Step {i}: {step['comment']}")
            
            # PASS tech_info to execute_step
            await PlaywrightExecutor.execute_step(page, step, tech_info)
            
            if step.get("action") == "extract" and "extracted_data" in step:
                extracted_data = step["extracted_data"]
                print(f"     Extracted {len(extracted_data)} items")
                if extracted_data:
                    # Limit output for readability
                    sample = json.dumps(extracted_data[0], indent=2)[:200]
                    print(f"     Sample: {sample}...")
                break  # Exit after first successful extraction for testing
        
        # Return success based on whether we extracted data
        return extracted_data is not None and len(extracted_data) > 0

async def main():
    test_cases = [
        ("https://blog.crewai.com/build-agents-to-be-dependable/", 
         "Extract the article title and content"),
        ("https://www.wikipedia.org/wiki/Artificial_intelligence", 
         "Extract the main article sections"),
    ]
    
    for url, task in test_cases:
        success = await test_planning_flow(url, task)
        if success:
            print("✅ Test passed")
        else:
            print("❌ Test failed")
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
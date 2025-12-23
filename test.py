# test_wappalyzer_final.py
import asyncio
from playwright.async_api import async_playwright
from Wappalyzer import Wappalyzer, WebPage

async def test():
    """Test the correct Wappalyzer usage"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        url = "https://blog.crewai.com/build-agents-to-be-dependable/"
        await page.goto(url, wait_until="networkidle")
        
        # Get response object
        response = await page.request.get(url)
        
        # Initialize Wappalyzer
        wappalyzer = Wappalyzer.latest()
        
        try:
            # CORRECT METHOD
            webpage = WebPage.new_from_response(response)
            tech = wappalyzer.analyze(webpage)
            
            print(f"✅ Success! Detected {len(tech)} technologies:")
            for tech_name, tech_info in tech.items():
                categories = tech_info.get('categories', [])
                print(f"  - {tech_name}: {categories}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
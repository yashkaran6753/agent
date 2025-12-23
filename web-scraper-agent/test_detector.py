#!/usr/bin/env python3
#python test_detector.py
"""
Robust test script for FrameworkDetector
Tests various website types with different tech stacks
"""

import asyncio
import sys
from pathlib import Path
import warnings

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Suppress Wappalyzer warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message="Caught.*compiling regex")

from playwright.async_api import async_playwright
from src.frameworks.detector import FrameworkDetector

class TechStackTester:
    def __init__(self):
        self.test_cases = [
            # Category 1: Traditional CMS / Static Sites
            {
                "url": "https://blog.crewai.com/build-agents-to-be-dependable/",
                "name": "Ghost CMS Blog",
                "expected": ["Ghost", "Ghost-powered"]
            },
            {
                "url": "https://www.whitehouse.gov/",
                "name": "WhiteHouse (WordPress)",
                "expected": ["WordPress", "WordPress-powered"]
            },
            
            # Category 2: React SPAs
            {
                "url": "https://react.dev/",  # Updated React docs URL
                "name": "React Documentation",
                "expected": ["Next.js", "Server-Side Rendered"]
            },
            {
                "url": "https://vercel.com/",
                "name": "Vercel (Next.js)",
                "expected": ["Next.js", "React", "Single Page Application"]
            },
            
            # Category 3: Vue.js SPAs
            {
                "url": "https://vuejs.org/",
                "name": "Vue.js Documentation",
                "expected": ["Vue.js", "Single Page Application"]
            },
            {
                "url": "https://nuxt.com/",
                "name": "Nuxt.js Documentation",
                "expected": ["Nuxt.js", "Vue", "Single Page Application"]
            },
            
            # Category 4: Traditional Websites
            {
                "url": "https://www.wikipedia.org/",
                "name": "Wikipedia",
                "expected": ["Static site", "None detected"]
            },
            {
                "url": "https://www.python.org/",
                "name": "Python.org",
                "expected": ["Traditional", "None detected"]
            },
            
            # Category 5: E-commerce
            {
                "url": "https://www.shopify.com/",
                "name": "Shopify",
                "expected": ["Traditional website"]
            },
            
            # Category 6: Heavy Bot Protection
            {
                "url": "https://www.cloudflare.com/",
                "name": "Cloudflare",
                "expected": ["Cloudflare", "Bot protection", "Cached"]
            },
            
            # Category 7: Modern Apps
            {
                "url": "https://www.linear.app/",
                "name": "Linear.app",
                "expected": ["React", "SPA", "API"]
            },
            
            # Edge Cases
            {
                "url": "https://news.ycombinator.com/",
                "name": "Hacker News",
                "expected": ["Static site", "None detected"]
            },
            {
                "url": "https://stackoverflow.com/",
                "name": "Stack Overflow",
                "expected": ["Traditional", "jQuery"]
            }
        ]
    
    async def test_single_website(self, url: str, name: str, expected: list):
        """Test tech stack detection for a single URL."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            print(f"\n{'='*60}")
            print(f"🌐 Testing: {name}")
            print(f"📎 URL: {url}")
            
            try:
                # Set reasonable timeout
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Get tech stack analysis
                tech_info = await FrameworkDetector._analyze_tech_stack(page)
                summary = FrameworkDetector._format_tech_summary(tech_info)
                
                # Print results
                print(f"📊 DETECTION RESULT: {summary}")
                
                # Check if expected keywords are found
                found_keywords = []
                missing_keywords = []
                
                for keyword in expected:
                    if keyword.lower() in summary.lower():
                        found_keywords.append(keyword)
                    else:
                        missing_keywords.append(keyword)
                
                # Print validation
                if found_keywords:
                    print(f"✅ Found expected: {', '.join(found_keywords)}")
                
                if missing_keywords:
                    print(f"❌ Missing expected: {', '.join(missing_keywords)}")
                
                # Show detected technologies from Wappalyzer
                if tech_info.get("wappalyzer"):
                    tech_list = list(tech_info["wappalyzer"])
                    if tech_list:
                        print(f"🔧 Wappalyzer detected: {', '.join(sorted(tech_list)[:10])}{'...' if len(tech_list) > 10 else ''}")
                
                # Show some raw detection flags
                interesting_flags = {
                    "react": tech_info.get("react"),
                    "vue": tech_info.get("vue"),
                    "angular": tech_info.get("angular"),
                    "nextjs": tech_info.get("nextjs"),
                    "nuxt": tech_info.get("nuxt"),
                    "script_count": tech_info.get("script_count"),
                    "is_static": tech_info.get("is_static"),
                    "cached": tech_info.get("cached"),
                }
                print(f"📈 Key flags: {interesting_flags}")
                
                return True, summary
                
            except Exception as e:
                print(f"❌ ERROR: {str(e)[:100]}")
                return False, str(e)
                
            finally:
                await browser.close()
    
    async def run_all_tests(self):
        """Run all test cases."""
        print("🚀 Starting FrameworkDetector Test Suite")
        print(f"📋 Testing {len(self.test_cases)} websites")
        print(f"{'='*60}")
        
        results = []
        passed = 0
        failed = 0
        
        for test_case in self.test_cases:
            success, result = await self.test_single_website(
                test_case["url"],
                test_case["name"],
                test_case["expected"]
            )
            
            if success:
                passed += 1
                results.append((test_case["name"], "PASS", result))
            else:
                failed += 1
                results.append((test_case["name"], "FAIL", result))
            
            # Small delay between tests
            await asyncio.sleep(1)
        
        # Print summary
        print(f"\n{'='*60}")
        print("📊 TEST SUMMARY")
        print(f"{'='*60}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"📈 Success Rate: {(passed/len(self.test_cases)*100):.1f}%")
        
        # Show detailed results
        print(f"\n📋 Detailed Results:")
        for name, status, result in results:
            status_symbol = "✅" if status == "PASS" else "❌"
            print(f"{status_symbol} {name}: {result[:80]}{'...' if len(str(result)) > 80 else ''}")
        
        return passed, failed

async def main():
    """Main test runner."""
    tester = TechStackTester()
    passed, failed = await tester.run_all_tests()
    
    # Exit with error code if any tests failed
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
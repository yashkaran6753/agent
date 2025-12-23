# src/utils/paginator.py  (FIXED: max_pages default + stop when duplicates detected)
from playwright.async_api import Page
from loguru import logger
import random  # Added for human-like delays

class Paginator:
    @staticmethod
    async def auto_paginate(
        page: Page, 
        extract_fn, 
        max_pages: int = 10,  # Default: stop after 10 pages (prevent infinite loops)
        next_text: str = "Next"
    ) -> list:
        """
        Generic pagination that:
        - Clicks "Next" or scrolls
        - Stops when max_pages reached OR no new UNIQUE data
        - Returns aggregated data
        """
        all_data = []
        seen_hashes = set()  # Track unique items by hash
        page_num = 1

        while page_num <= max_pages:
            logger.info(f"📄 Scraping page {page_num}/{max_pages}")
            
            # Scroll to load lazy content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(random.randint(1000, 3000))  # Human-like delay: 1-3s
            
            # Extract data
            new_data = await extract_fn(page)
            
            # Check for duplicates (deduplicate by text content)
            unique_new = []
            for item in new_data:
                item_hash = hash(str(item))
                if item_hash not in seen_hashes:
                    seen_hashes.add(item_hash)
                    unique_new.append(item)
            
            if not unique_new:
                logger.info("No new unique data – stopping pagination")
                break
                
            all_data.extend(unique_new)

            # Try "Next" button - more specific selectors
            next_selectors = [
                "a:has-text('Next')",
                "a:has-text('Next page')", 
                "button:has-text('Next')",
                "[class*='next']",
                "[class*='pagination'] a:last-child",
                "a[rel='next']",
                "[aria-label*='Next']"
            ]
            
            next_btn = None
            for selector in next_selectors:
                candidate = page.locator(selector).first
                if await candidate.count() > 0 and await candidate.is_visible():
                    next_btn = candidate
                    break
            
            if next_btn:
                await next_btn.click()
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(random.randint(1000, 3000))  # Human-like delay after click
                page_num += 1
                continue

            # Fallback: scroll to bottom (infinite scroll)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            await page.wait_for_timeout(random.randint(1000, 3000))  # Additional delay
            page_num += 1

        if page_num > max_pages:
            logger.warning(f"Reached max pages ({max_pages}) – stopping pagination")
            
        logger.success(f"Pagination complete: {len(all_data)} unique items")
        return all_data
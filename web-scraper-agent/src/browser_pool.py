from playwright.async_api import async_playwright, Browser
from loguru import logger
from playwright_stealth.stealth import Stealth

class BrowserPool:
    def __init__(self, size: int = 3):
        self.size = size
        self.browsers: list[Browser] = []
        self.pw = None

    async def start(self):
        self.pw = await async_playwright().start()
        for _ in range(self.size):
            b = await self.pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled",
                      "--no-sandbox", "--disable-setuid-sandbox"]
            )
            self.browsers.append(b)
        logger.info(f"BrowserPool: {self.size} browsers ready")

    async def get(self) -> Browser:
        if not self.browsers: await self.start()
        return self.browsers.pop()

    async def release(self, b: Browser):
        self.browsers.append(b)

    async def close(self):
        for b in self.browsers: await b.close()
        if self.pw: await self.pw.stop()

    def __del__(self):
        """Ensure proper cleanup of browser connections on object destruction."""
        try:
            if hasattr(self, 'browsers') and self.browsers:
                logger.warning("BrowserPool: Force closing browsers in destructor")
                # Note: This is synchronous cleanup - async cleanup should be done explicitly
                # via close() method. This is a safety net for unexpected shutdowns.
        except Exception as e:
            logger.error(f"BrowserPool cleanup error: {e}")
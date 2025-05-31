# browser.py

import os
import time
import logging
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROXY_SERVER = os.getenv("PROXY_SERVER", "")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

def screenshot_url(url, path="screenshot.jpg", wait_seconds=3, headless=True):
    def try_browser(browser_type):
        try:
            browser = browser_type.launch(
                headless=headless,
                proxy={
                    "server": PROXY_SERVER,
                    "username": PROXY_USERNAME,
                    "password": PROXY_PASSWORD,
                }
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/113.0.0.0 Safari/537.36"
                ),
                viewport={'width': 1280, 'height': 800},
                locale='en-US',
                java_script_enabled=True,
                timezone_id='America/New_York',
            )

            # Fake non-headless environment
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                // Remove modal popups (non-cookie)
                setInterval(() => {
                    const modals = document.querySelectorAll('div[role="dialog"], .popup, .modal, .overlay');
                    modals.forEach(el => el.style.display = 'none');
                }, 1000);
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """)

            # Remove common popups
            context.add_init_script("""
                const removeAnnoyances = () => {
                    const selectors = [
                        'div[role="dialog"]', '.popup', '.modal', '.overlay', '.backdrop',
                        '[data-testid="sheetDialog"]', '.fc-consent-root',
                        '[id^="modal"]', '.ytp-popup', '.ytp-modal-dialog',
                        '.RveJvd.snByac', '.Ax4B8.ZAGvjd',
                        'div[style*="z-index"][style*="position: fixed"]'
                    ];
                    selectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el.remove());
                    });

                    document.querySelectorAll('*').forEach(el => {
                        const style = getComputedStyle(el);
                        if (style.zIndex > 1000 && style.position === 'fixed') {
                            el.style.display = 'none';
                        }
                    });
                };
                setInterval(removeAnnoyances, 1000);
            """)

            page = context.new_page()

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except PlaywrightTimeoutError:
                logger.warning("Timeout during page.goto with 'networkidle'. Retrying with 'load'")
                try:
                    page.goto(url, wait_until="load", timeout=30000)
                except PlaywrightTimeoutError as e:
                    logger.error(f"Page.goto failed again with timeout: {e}")
                    browser.close()
                    return False

            time.sleep(wait_seconds)

            # Try cookie banner dismissals
            for selector in [
                'button:has-text("Accept")',
                'button:has-text("Accept All")',
                '.cookie-accept',
                '[aria-label="Accept cookies"]',
                '[id*="onetrust"] button:has-text("Accept")',
            ]:
                try:
                    page.locator(selector).click(timeout=1000)
                    logger.info(f"Clicked cookie consent via: {selector}")
                    break
                except:
                    continue

            content = page.content()
            blocked_keywords = [
                "access denied", "blocked by", "network security", 
                "sign in to confirm", 
                "media could not be played"
                # "log in", "create an account", 
            ]
            if any(kw.lower() in content.lower() for kw in blocked_keywords):
                logger.warning("Page appears blocked or behind a login.")

            page.screenshot(path=path)
            logger.info(f"Screenshot saved to {path}")
            browser.close()
            return True
        except Exception as e:
            logger.error(f"Failed to screenshot with {browser_type.name}: {e}")
            return False

    with sync_playwright() as p:
        for browser_type in [p.chromium, p.firefox, p.webkit]:
            if try_browser(browser_type):
                return
        raise RuntimeError("All screenshot attempts failed.")
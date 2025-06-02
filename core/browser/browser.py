# browser.py

import time
import logging
import threading
from queue import Queue, Empty
from core.utils.config import Config
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

MAX_TABS = 5

def screenshot_url(url, path="screenshot.jpg", wait_seconds=3, headless=True):
    def try_browser(browser_type):
        browser = None
        context = None
        try:
            browser = browser_type.launch(
                headless=headless,
                proxy={
                    "server": Config.PROXY_SERVER,
                    "username": Config.PROXY_USERNAME,
                    "password": Config.PROXY_PASSWORD,
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

            # Anti-bot + modal blockers
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                const hideStuff = () => {
                    const selectors = [
                        'div[role="dialog"]', '.popup', '.modal', '.overlay',
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
                setInterval(hideStuff, 1000);
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
                    return False

            time.sleep(wait_seconds)

            # Dismiss cookie modals
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
                "sign in to confirm", "media could not be played"
            ]
            if any(kw in content.lower() for kw in blocked_keywords):
                logger.warning("Page appears blocked or behind a login.")

            page.screenshot(path=path)
            logger.info(f"Screenshot saved to {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to screenshot with {browser_type.name}: {e}")
            return False

        finally:
            if context:
                try:
                    context.close()
                except Exception as e:
                    logger.warning(f"Failed to close context cleanly: {e}")
            if browser:
                try:
                    browser.close()
                except Exception as e:
                    logger.warning(f"Failed to close browser cleanly: {e}")

    with sync_playwright() as p:
        for browser_type in [p.chromium]:  # Limit to Chromium for stability
            if try_browser(browser_type):
                return
        raise RuntimeError("All screenshot attempts failed.")
    
class BrowserManager:
    def __init__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True,
            proxy={
                "server": Config.PROXY_SERVER,
                "username": Config.PROXY_USERNAME,
                "password": Config.PROXY_PASSWORD,
            }
        )
        self.lock = threading.Lock()
        self.tab_queue = Queue(maxsize=MAX_TABS)

    def _create_context(self):
        return self.browser.new_context(
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

    def screenshot_url(self, url, path="screenshot.jpg", wait_seconds=3):
        if self.tab_queue.full():
            raise RuntimeError("Max number of tabs reached. Try again shortly.")

        self.tab_queue.put(1)  # Reserve tab
        try:
            context = self._create_context()
            page = context.new_page()

            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                const hideStuff = () => {
                    const selectors = [
                        'div[role="dialog"]', '.popup', '.modal', '.overlay',
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
                setInterval(hideStuff, 1000);
            """)

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except PlaywrightTimeoutError:
                logger.warning("Timeout during page.goto with 'networkidle'. Retrying with 'load'")
                try:
                    page.goto(url, wait_until="load", timeout=30000)
                except PlaywrightTimeoutError as e:
                    logger.error(f"Page.goto failed again with timeout: {e}")
                    return False

            time.sleep(wait_seconds)

            # Try dismissing cookie modals
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

            page.screenshot(path=path)
            logger.info(f"Screenshot saved to {path}")
            return True
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return False
        finally:
            try:
                context.close()
            except Exception as e:
                logger.warning(f"Context close failed: {e}")
            self.tab_queue.get_nowait()

    def shutdown(self):
        self.browser.close()
        self.playwright.stop()


# Singleton instance
_browser_manager = BrowserManager()

def screenshot_url(url, path="screenshot.jpg", wait_seconds=3, headless=True):
    return _browser_manager.screenshot_url(url, path=path, wait_seconds=wait_seconds)

def shutdown_browser():
    _browser_manager.shutdown()
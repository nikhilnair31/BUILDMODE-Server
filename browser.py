import time
import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def screenshot_url(url, path="screenshot.jpg", wait_seconds=3):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # 👈 headless=False to seem real
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",  # 👈 pretend to be Chrome
            viewport={'width': 1280, 'height': 800},  # 👈 normal screen size
            locale='en-US',
            java_script_enabled=True,
            timezone_id='America/New_York',
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            // Remove modal popups (non-cookie)
            setInterval(() => {
                const modals = document.querySelectorAll('div[role="dialog"], .popup, .modal, .overlay');
                modals.forEach(el => el.style.display = 'none');
            }, 1000);
        """)
        page = context.new_page()

        page.goto(url, wait_until="networkidle")
        time.sleep(wait_seconds)  # Let it fully render

        # Dismiss cookie banners
        for selector in [
            'button:has-text("Accept")', 
            'button:has-text("Accept All")', 
            '.cookie-accept', 
            '[aria-label="Accept cookies"]'
        ]:
            try:
                page.locator(selector).click(timeout=1000)
                break
            except:
                pass

        if "login" in page.url:
            logger.error("Blocked by login wall")
            raise Exception("Blocked by login wall")

        page.screenshot(path=path)
        browser.close()
import os
import re
import hashlib
import asyncio
from playwright.async_api import async_playwright
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGET_URLS = [
    # 'https://youtu.be/3VJT2JeDCyw',
    # 'https://youtube.com/shorts/9VZKdxRKI-8',
    # 'https://www.reddit.com/r/DC_Cinematic/s/hy82tXRDtn',
    # 'https://www.reddit.com/r/Doom/s/tVSqQ1XNqM',
    # 'https://www.reddit.com/r/jobs/s/XXP8wgIRGx',
    # 'https://www.instagram.com/reel/DIelBMXTwXY/?igsh=MWR3Y2Z3bWkzdGQzNQ==',
    # 'https://fxtwitter.com/ritwikpavan/status/1928181158598042080',
    # 'https://fxtwitter.com/Rj2weak/status/1924587554822660408',
    'https://fxtwitter.com/garrytan/status/1928179754353483821',
]

PROXY_SERVER = "geo.iproyal.com:12321"
PROXY_USERNAME = "df7p5lapZejkbGxb"
PROXY_PASSWORD = "zxeQ4kCT7WUDts9K_country-us"

OUTPUT_DIR = "./screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_async(func):
    try:
        return asyncio.run(func)
    except RuntimeError:
        return asyncio.get_event_loop().run_until_complete(func)

def sanitize_filename(url):
    hostname = url.split('//')[1].split('/')[0]
    url_hash = hashlib.md5(url.encode()).hexdigest()[:6]
    return re.sub(r'[^\w\-_\. ]', '_', f"{hostname}_{url_hash}.jpg")

def screenshot_url(url, path="screenshot.jpg", wait_seconds=2):
    run_async(_screenshot_url(url, path, wait_seconds))

async def _screenshot_url(url, path, wait_seconds):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={
                "server": PROXY_SERVER,
                "username": PROXY_USERNAME,
                "password": PROXY_PASSWORD,
            }
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/113.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
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

        page = await context.new_page()
        try:
            print(f"🌐 Visiting: {url}")
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(wait_seconds * 1000)
            await page.screenshot(path=path)
        finally:
            await browser.close()

def safe_screenshot(url):
    filename = sanitize_filename(url)
    screenshot_path = os.path.join(OUTPUT_DIR, filename)
    try:
        screenshot_url(url, path=screenshot_path, wait_seconds=2)
        return f"✅ Screenshot saved to {screenshot_path}"
    except Exception as e:
        return f"❌ Failed for {url}: {e}"

if __name__ == "__main__":
    max_workers = min(4, len(TARGET_URLS))  # Adjust thread count based on your system
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(safe_screenshot, url) for url in TARGET_URLS]
        for future in as_completed(futures):
            print(future.result())

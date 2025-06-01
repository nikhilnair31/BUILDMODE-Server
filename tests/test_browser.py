# test_browser.py

import sys
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.browser.browser import screenshot_url

TARGET_URLS = [
    # 'https://www.google.com/search?client=ms-android-google&sca_esv=f37af7071d948b3e&sxsrf=AHTn8zpGZRNViWdXhEieyTFYiyNlwT1oMg:1747748707062&udm=2&fbs=ABzOT_DnPN66xNYYiVBYF80MNa9-mD9FW2KvyJ7Ee6i9AfRy7R1eW7fYkhs9lmIjuzf1c814hZBiGsd-xVdQMnO74TAYG6xVs_Jf6ReezTSHZRPh3_w0bBX_usS_cVABLSvTy-g77wOYE-5sKMlfUjz3Mk7JzD5YpsEgzF3hjloZGfrIdTU197bRF-FVoEQwZ9uzNuKy6VZ0ibRhiueJ-W5klyY-kVjnKb5u2mW7lTRXX0F25uESjF0&q=mymind&sa=X&sqi=2&ved=2ahUKEwiagt2ml7KNAxW4EVkFHdqzNJ8QtKgLegQIGxAB&biw=411&bih=784&dpr=2.63',
    
    'https://youtu.be/3VJT2JeDCyw',
    'https://youtube.com/shorts/9VZKdxRKI-8',

    'https://www.reddit.com/r/DC_Cinematic/s/hy82tXRDtn',
    'https://www.reddit.com/r/Doom/s/tVSqQ1XNqM',
    'https://www.reddit.com/r/jobs/s/XXP8wgIRGx',

    'https://www.instagram.com/reel/DIelBMXTwXY/?igsh=MWR3Y2Z3bWkzdGQzNQ==',

    'https://fxtwitter.com/ritwikpavan/status/1928181158598042080',
    'https://fxtwitter.com/Rj2weak/status/1924587554822660408',
]

OUTPUT_DIR = "./screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def safe_screenshot(url):
    try:
        filename = f"{url.split('//')[1].split('/')[0]}.jpg"
        screenshot_path = os.path.join(OUTPUT_DIR, filename)
        screenshot_url(url, path=screenshot_path, wait_seconds=2)
        return f"✅ Screenshot saved to {screenshot_path}"
    except Exception as e:
        return f"❌ Failed for {url}: {e}\n{traceback.format_exc()}"

def main():
    max_workers = min(8, len(TARGET_URLS))  # Adjust based on your CPU/RAM
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(safe_screenshot, url) for url in TARGET_URLS]
        for future in as_completed(futures):
            print(future.result())

if __name__ == "__main__":
    main()
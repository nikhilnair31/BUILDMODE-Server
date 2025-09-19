# test_image_resizer.py

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.content.images import compress_image

UPLOADS_DIR = "uploads"
MAX_SIZE_KB = 500
MAX_WORKERS = 4

def process_file(path, file):
    try:
        size_kb = os.path.getsize(path) / 1024
        if size_kb <= MAX_SIZE_KB:
            return f"[-] Skipped: {path} ({size_kb:.1f} KB)"

        # Always force compress to JPEG
        new_path = compress_image(path, max_size_kb=MAX_SIZE_KB)
        if new_path:
            new_size_kb = os.path.getsize(new_path) / 1024
            return f"[+] {path}: {size_kb:.1f} KB -> {new_size_kb:.1f} KB"
        else:
            return f"[!] Compression failed: {path}"
    except Exception as e:
        return f"[!] Error processing {path}: {e}"

def resize_large_images():
    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for root, _, files in os.walk(UPLOADS_DIR):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
                    continue
                path = os.path.join(root, file)
                tasks.append(executor.submit(process_file, path, file))

        for future in as_completed(tasks):
            print(future.result())

if __name__ == "__main__":
    resize_large_images()


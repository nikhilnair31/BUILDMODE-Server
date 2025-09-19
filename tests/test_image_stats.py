# test_image_stats.py

import os
import statistics

# Directory to scan – change as needed
TARGET_DIR = "uploads"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

def collect_image_sizes(directory):
    sizes = []
    files = []

    for fname in os.listdir(directory):
        fpath = os.path.join(directory, fname)
        if not os.path.isfile(fpath):
            continue

        ext = os.path.splitext(fname.lower())[1]
        if ext not in IMAGE_EXTS:
            continue

        size_kb = os.path.getsize(fpath) / 1024
        sizes.append(size_kb)
        files.append((fname, size_kb))

    # sort by size descending
    files.sort(key=lambda x: x[1], reverse=False)
    return files, sizes

def print_stats(files, sizes):
    if not sizes:
        print("No image files found.")
        return

    print(f"\nFound {len(files)} images\n")
    for fname, size in files:
        print(f"{fname:40s} {size:8.2f} KB")

    print("\n--- Stats ---")
    print(f"Total size: {sum(sizes)/1024:.2f} MB")
    print(f"Average:    {statistics.mean(sizes):.2f} KB")
    print(f"Median:     {statistics.median(sizes):.2f} KB")
    print(f"Min:        {min(sizes):.2f} KB")
    print(f"Max:        {max(sizes):.2f} KB")

if __name__ == "__main__":
    if not os.path.isdir(TARGET_DIR):
        print(f"Directory not found: {TARGET_DIR}")
    else:
        files, sizes = collect_image_sizes(TARGET_DIR)
        print_stats(files, sizes)

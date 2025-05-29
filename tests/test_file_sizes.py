import os
import statistics
from collections import defaultdict

UPLOADS_DIR = "uploads"

def get_file_sizes_by_type(directory):
    file_sizes = defaultdict(list)

    for root, _, files in os.walk(directory):
        for file in files:
            filepath = os.path.join(root, file)
            if os.path.isfile(filepath):
                ext = os.path.splitext(file)[1].lower() or 'no_ext'
                size = os.path.getsize(filepath)
                file_sizes[ext].append(size)

    return file_sizes

def print_file_stats(file_sizes):
    for ext, sizes in file_sizes.items():
        sizes.sort()
        print(f"Extension: {ext}")
        print(f"  Count  : {len(sizes)}")
        print(f"  Min    : {min(sizes)} bytes")
        print(f"  Max    : {max(sizes)} bytes")
        print(f"  Avg    : {sum(sizes) / len(sizes):.2f} bytes")
        print(f"  Median : {statistics.median(sizes)} bytes")
        print()

if __name__ == "__main__":
    file_sizes_by_type = get_file_sizes_by_type(UPLOADS_DIR)
    if file_sizes_by_type:
        print_file_stats(file_sizes_by_type)
    else:
        print("No files found in uploads directory.")

import os

# Path to uploads folder in parent directory
uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")

# Allowed image extensions
image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}

for root, _, files in os.walk(uploads_dir):
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in image_exts:
            file_path = os.path.join(root, f)
            try:
                os.remove(file_path)
                print(f"Deleted: {file_path}")
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")
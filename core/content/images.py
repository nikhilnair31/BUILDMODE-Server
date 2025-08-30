# image.py

import io
import os
import uuid
import logging
from core.utils.config import Config
from werkzeug.utils import secure_filename
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def compress_image(tempfile, max_size_kb=500):
    """
    Compress an image to be under max_size_kb, preferring JPEG output.
    Uses binary search on quality for speed.
    """
    logger.info(f"Compressing image at {tempfile}")

    try:
        temp_path = tempfile.name if hasattr(tempfile, "name") else tempfile
        file_name = os.path.basename(temp_path)

        if "." not in file_name:
            logger.error(f"Invalid file name format: {file_name}")
            return None

        name, _ = os.path.splitext(file_name)
        final_filename = secure_filename(f"{name}.jpg")
        final_filepath = os.path.join(Config.UPLOAD_DIR, final_filename)

        img = Image.open(temp_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # --- quick shortcut: if file already small enough ---
        if os.path.getsize(temp_path) <= max_size_kb * 1024:
            img.save(final_filepath, format="JPEG", quality=85, optimize=True)
            logger.info(f"Image already small enough; saved as {final_filepath}")
            return final_filepath

        # --- if image is extremely large, downscale once ---
        max_pixels = 1920 * 1080  # cap size to ~1080p for speed
        if img.width * img.height > max_pixels:
            img.thumbnail((1920, 1080), Image.LANCZOS)

        # --- binary search for quality ---
        low, high = 10, 95
        best_bytes = None

        while low <= high:
            mid = (low + high) // 2
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=mid, optimize=True)
            size_kb = buffer.tell() / 1024

            if size_kb <= max_size_kb:
                best_bytes = buffer.getvalue()
                low = mid + 1  # try higher quality
            else:
                high = mid - 1  # lower quality

        # --- save best result ---
        if best_bytes:
            with open(final_filepath, "wb") as f:
                f.write(best_bytes)
            logger.info(f"Compressed image saved to {final_filepath} ({len(best_bytes)/1024:.1f} KB)")
            return final_filepath
        else:
            # fallback: save at lowest quality
            img.save(final_filepath, format="JPEG", quality=10, optimize=True)
            logger.warning(f"Fallback compression used for {final_filepath}")
            return final_filepath

    except Exception as e:
        logger.error(f"Failed to compress image at {tempfile}: {e}")
        return None

def generate_thumbnail(file_path):
    logger.info(f"Generating thumbnail for {file_path}")
    try:
        thumbnail_uuid = uuid.uuid4().hex
        ext = file_path.lower()
        dest_path = os.path.join(Config.THUMBNAIL_DIR, f"{thumbnail_uuid}.jpg")

        if ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            with Image.open(file_path) as img:
                img.thumbnail((300, 300))
                img.save(dest_path, "JPEG")
        else:
            return None  # unsupported
        
        final_thumbnail_path = os.path.join(Config.THUMBNAIL_DIR, f"{thumbnail_uuid}.jpg")
        logger.info(f"Thumbnail created at {final_thumbnail_path}")
        
        return final_thumbnail_path
    except Exception as e:
        logger.error(f"Failed to create thumbnail for {file_path}: {e}")
        return None
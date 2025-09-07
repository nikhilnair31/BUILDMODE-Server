# image.py

import json, base64, io, math, os, uuid, logging
from typing import Tuple
from typing import List, Optional
from core.utils.config import Config
from werkzeug.utils import secure_filename
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def encode_image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def compress_image(tempfile, max_size_kb=500):
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

def create_mosaic(image_paths, final_size=(800, 800), grid_size=None, bg_color=(255, 255, 255)):
    """
    Create a mosaic grid from input images.

    :param image_paths: List of file paths to images
    :param output_path: Path to save final mosaic
    :param final_size: (width, height) of the output mosaic
    :param grid_size: (cols, rows) - if None, will auto-square based on number of images
    :param bg_color: Background color for empty cells
    """
    num_images = len(image_paths)
    if num_images == 0:
        raise ValueError("No images provided")

    # Auto grid size if not given
    if grid_size is None:
        cols = math.ceil(math.sqrt(num_images))
        rows = math.ceil(num_images / cols)
    else:
        cols, rows = grid_size

    # Calculate each cell size
    cell_w = final_size[0] // cols
    cell_h = final_size[1] // rows

    # Create blank canvas
    mosaic = Image.new("RGB", final_size, bg_color)

    for idx, img_path in enumerate(image_paths):
        try:
            img = Image.open(img_path)
            img = img.convert("RGB")
            img.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)

            # Position inside the grid
            row, col = divmod(idx, cols)
            x = col * cell_w + (cell_w - img.width) // 2
            y = row * cell_h + (cell_h - img.height) // 2

            mosaic.paste(img, (x, y))
        except Exception as e:
            print(f"Skipping {img_path}: {e}")
    
    # Save to bytes
    buf = io.BytesIO()
    mosaic.save(buf, format="JPEG", quality=95)
    return buf.getvalue()
def create_tight_mosaic(image_paths, final_size=(800, 800), grid_size=None, bg_color=(255, 255, 255)):
    """
    Create a tightly packed mosaic (no spacing, no aspect ratio preserved).

    :param image_paths: List of file paths to images
    :param output_path: Path to save final mosaic
    :param final_size: (width, height) of the output mosaic
    :param grid_size: (cols, rows) - if None, will auto-square based on number of images
    :param bg_color: Fill background color if fewer images than grid cells
    """
    num_images = len(image_paths)
    if num_images == 0:
        raise ValueError("No images provided")

    # Auto grid size if not provided → square-ish layout
    if grid_size is None:
        cols = math.ceil(math.sqrt(num_images))
        rows = math.ceil(num_images / cols)
    else:
        cols, rows = grid_size

    cell_w = final_size[0] // cols
    cell_h = final_size[1] // rows

    # Create base image
    mosaic = Image.new("RGB", final_size, bg_color)

    for idx, img_path in enumerate(image_paths):
        if idx >= cols * rows:
            break  # if more images than cells, ignore the rest

        try:
            img = Image.open(img_path).convert("RGB")
            # Force resize exactly to cell
            img = img.resize((cell_w, cell_h), Image.Resampling.LANCZOS)

            row, col = divmod(idx, cols)
            x = col * cell_w
            y = row * cell_h

            mosaic.paste(img, (x, y))
        except Exception as e:
            print(f"Skipping {img_path}: {e}")
    
    # Save to bytes
    buf = io.BytesIO()
    mosaic.save(buf, format="JPEG", quality=95)
    return buf.getvalue()
def create_crop_mosaic(image_paths: List[str], final_size: Tuple[int, int] = (900, 300), grid_size: Optional[Tuple[int, int]] = None, bg_color=(255, 255, 255)) -> str:
    """
    Create a mosaic that preserves aspect ratio by cropping to fit each cell.

    :param image_paths: List of file paths to images
    :param output_path: Path to save final mosaic
    :param final_size: (width, height) of the output mosaic
    :param grid_size: (cols, rows). If None, will be auto-squared.
    :param bg_color: Background color if not filled completely
    """
    num_images = len(image_paths)
    if num_images == 0:
        raise ValueError("No images provided")

    # Auto grid (still good default for tight packing)
    if grid_size is None:
        cols = math.ceil(math.sqrt(num_images))
        rows = math.ceil(num_images / cols)
    else:
        cols, rows = grid_size

    cell_w = final_size[0] // cols
    cell_h = final_size[1] // rows

    # Limit to number of available slots
    max_images = cols * rows
    image_paths = image_paths[:max_images]

    mosaic = Image.new("RGB", final_size, bg_color)

    for idx, img_path in enumerate(image_paths):
        try:
            img = Image.open(img_path).convert("RGB")

            # Scale to fill cell (may overhang one dimension)
            scale = max(cell_w / img.width, cell_h / img.height)
            new_w, new_h = int(img.width * scale), int(img.height * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Crop center to cell size
            left = (new_w - cell_w) // 2
            top = (new_h - cell_h) // 2
            img = img.crop((left, top, left + cell_w, top + cell_h))

            row, col = divmod(idx, cols)
            x = col * cell_w
            y = row * cell_h
            mosaic.paste(img, (x, y))

        except Exception as e:
            print(f"Skipping {img_path}: {e}")
    
    # Save to bytes
    buf = io.BytesIO()
    mosaic.save(buf, format="JPEG", quality=95)
    return buf.getvalue()
def create_pinterest_mosaic(image_paths, final_size=(900, 600), target_row_height=200, bg_color=(255, 255, 255)):
    """
    Create a Pinterest-style mosaic (justified rows, preserving aspect ratio).
    Last incomplete row is discarded to avoid empty space.

    :param image_paths: List of file paths to images
    :param output_path: Path to save final mosaic
    :param final_size: (width, height) of the output canvas
    :param target_row_height: Approximate row height for images
    :param bg_color: Background fill color
    """
    canvas_w, canvas_h = final_size
    valid_paths = [p for p in image_paths if p and os.path.isfile(p)]
    if not valid_paths:
        # Return a tiny valid JPEG to avoid errors upstream
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), bg_color).save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    mosaic = Image.new("RGB", final_size, bg_color)

    row, row_width = [], 0
    y_offset = 0

    for path in image_paths:
        try:
            img = Image.open(path).convert("RGB")
            aspect = img.width / img.height
            scaled_w = int(aspect * target_row_height)
            row.append((img, aspect))
            row_width += scaled_w

            # Flush row when "full enough"
            if row_width >= canvas_w:
                total_aspect = sum(a for _, a in row)
                row_h = int(canvas_w / total_aspect)

                # Check if this row fits vertically
                if y_offset + row_h > canvas_h:
                    break  # stop, no partial rows

                # Render row
                x_offset = 0
                for im, aspect in row:
                    w = int(aspect * row_h)
                    resized = im.resize((w, row_h), Image.Resampling.LANCZOS)
                    mosaic.paste(resized, (x_offset, y_offset))
                    x_offset += w

                y_offset += row_h
                row, row_width = [], 0  # reset
        except Exception as e:
            print(f"Skipping {path}: {e}")

    # Render leftover partial row if any space remains
    if row and y_offset < canvas_h:
        total_aspect = sum(a for _, a in row)
        row_h = min(target_row_height, canvas_h - y_offset)
        if row_h > 0:
            x_offset = 0
            for im, a in row:
                w = int(a * row_h)
                resized = im.resize((w, row_h), Image.Resampling.LANCZOS)
                mosaic.paste(resized, (x_offset, y_offset))
                x_offset += w
            y_offset += row_h

    # If still nothing rendered, return tiny JPEG
    if y_offset <= 0:
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), bg_color).save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    # Crop vertically to filled space
    mosaic = mosaic.crop((0, 0, canvas_w, y_offset))

    # Save to bytes
    buf = io.BytesIO()
    mosaic.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

def rgb_to_lab(r,g,b):
    # sRGB to CIE Lab (D65)
    def inv_gamma(u): return u/12.92 if u<=0.04045 else ((u+0.055)/1.055)**2.4
    R,G,B = [inv_gamma(x/255.0) for x in (r,g,b)]
    X = 0.4124564*R + 0.3575761*G + 0.1804375*B
    Y = 0.2126729*R + 0.7151522*G + 0.0721750*B
    Z = 0.0193339*R + 0.1191920*G + 0.9503041*B
    X/=0.95047; Y/=1.00000; Z/=1.08883
    def f(t): return t**(1/3) if t>0.008856 else (7.787*t+16/116)
    fx, fy, fz = f(X), f(Y), f(Z)
    L = 116*fy - 16
    a = 500*(fx-fy)
    b = 200*(fy-fz)
    return [L,a,b]
def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2],16) for i in (0,2,4))
def call_col_vec(extracted_content: str):
    try:
        if isinstance(extracted_content, str):
            data = json.loads(extracted_content)
        else:
            data = extracted_content
    except Exception:
        return []

    colors = data.get("accent_colors", []) if isinstance(data, dict) else []
    results = []
    for hex_code in colors:
        try:
            rgb = hex_to_rgb(hex_code)
            lab = rgb_to_lab(*rgb)
            results.append({"hex": hex_code, "lab": lab})
        except Exception:
            continue
    return results
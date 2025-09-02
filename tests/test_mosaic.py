import base64
import math
from PIL import Image
from sqlalchemy import func, and_
from datetime import UTC, datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from core.database.database import get_db_session
from core.database.models import DataEntry
from core.notifications.emails import send_email

def create_mosaic(image_paths, output_path, final_size=(800, 800), grid_size=None, bg_color=(255, 255, 255)):
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

    mosaic.save(output_path)
    return output_path
def create_tight_mosaic(image_paths, output_path, final_size=(800, 800), grid_size=None, bg_color=(255, 255, 255)):
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

    mosaic.save(output_path, quality=95)
    return output_path
def create_crop_mosaic(
    image_paths: List[str],
    output_path: str,
    final_size: Tuple[int, int] = (900, 300),
    grid_size: Optional[Tuple[int, int]] = None,
    bg_color=(255, 255, 255)
) -> str:
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

    mosaic.save(output_path, quality=95)
    return output_path
def create_pinterest_mosaic(
    image_paths,
    output_path,
    final_size=(900, 600),
    target_row_height=200,
    bg_color=(255, 255, 255)
):
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
    mosaic = Image.new("RGB", final_size, bg_color)

    rows = []
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

    # Crop vertically to filled space (no empty bands at bottom)
    mosaic = mosaic.crop((0, 0, canvas_w, y_offset))
    mosaic.save(output_path, quality=95)
    return output_path

def epoch_range(period: str) -> Tuple[int,int,int,int]:
    now = datetime.now(UTC)
    if period == "weekly":
        start = now - timedelta(days=7)
        prev_start = start - timedelta(days=7)
    else:  # monthly
        start = now - timedelta(days=30)
        prev_start = start - timedelta(days=30)
    return int(start.timestamp()), int(now.timestamp()), int(prev_start.timestamp()), int(start.timestamp())

def image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

period_start, period_end, prev_start, prev_end = epoch_range("weekly")

session = get_db_session()

now_rows: List[DataEntry] = session.query(DataEntry) \
    .filter(
        and_(
            DataEntry.user_id == 1,
            DataEntry.timestamp >= period_start,
            DataEntry.timestamp < period_end
        )
    ) \
    .order_by(DataEntry.timestamp.desc()) \
    .limit(1000) \
    .all()

images = [row.file_path for row in now_rows]
output = create_pinterest_mosaic(images, "mosaic.jpg", final_size=(1200, 400))
print("Mosaic saved at:", output)

with open("mosaic.jpg", "rb") as f:
    img_bytes = f.read()

html = """
<html>
  <body>
    <h2>Your Mosaic</h2>
    <p>Here’s your personalized mosaic:</p>
    <img src="cid:mosaic1">
  </body>
</html>
"""

send_email(
    "niknair31898@gmail.com",
    "Your Mosaic",
    html_body=html,
    inline_images={"mosaic1": img_bytes}
)
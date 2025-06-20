# image.py

import io
import os
import uuid
import fitz
import base64
import logging
import numpy as np
from sklearn.cluster import KMeans
from core.utils.config import Config
from pdf2image import convert_from_path
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont
from colormath.color_diff import delta_e_cie2000
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def rgb_to_lab(rgb):
    srgb = sRGBColor(rgb[0]/255, rgb[1]/255, rgb[2]/255)
    return convert_color(srgb, LabColor)

def merge_similar_colors(colors, threshold=20):
    distinct = []
    for color in colors:
        lab1 = rgb_to_lab(color)
        if all(delta_e_cie2000(lab1, rgb_to_lab(other)) > threshold for other in distinct):
            distinct.append(color)
    return distinct

def extract_distinct_colors(image_path, num_clusters=30, num_colors=10, merge_threshold=20):
    image = Image.open(image_path).convert('RGB')
    image = image.resize((100, 100))  # speed
    pixels = np.array(image).reshape(-1, 3)

    kmeans = KMeans(n_clusters=num_clusters, random_state=42).fit(pixels)
    centers = kmeans.cluster_centers_.astype(int)

    merged = merge_similar_colors(centers, threshold=merge_threshold)
    merged = sorted(merged, key=lambda c: -np.sum((pixels == c).all(axis=1)))  # sort by frequency

    # Count frequency of each merged color
    color_counts = []
    for color in merged:
        mask = np.linalg.norm(pixels - color, axis=1) < merge_threshold
        count = np.sum(mask)
        color_counts.append((color, count))

    # Sort by count descending
    color_counts.sort(key=lambda x: -x[1])
    top_colors = [tuple(map(int, color)) for color, _ in color_counts[:num_colors]]
    print(f"Num of colors: {num_colors}")
    print(f"Distinct colors: {top_colors}")

    # Pad to fixed length
    flat_rgb = [v for color in top_colors for v in color]
    padded_rgb = flat_rgb + [0] * (3 * num_colors - len(flat_rgb))
    print(f"Padded RGB: {padded_rgb}")

    flat_rgb = [v / 255.0 for color in top_colors for v in color]  # normalize to [0,1]
    padded_rgb = flat_rgb + [0.0] * (3 * num_colors - len(flat_rgb))
    return padded_rgb

def generate_img_b64_list(save_path):
    # ✅ Load PDF and convert each page to JPEG base64
    doc = fitz.open(save_path)
    if doc.page_count == 0:
        return None

    image_b64_list = []
    for page in doc:
        pix = page.get_pixmap()
        image_bytes = pix.tobytes("jpeg")
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_b64_list.append(image_b64)

    doc.close()
    
    return image_b64_list

def compress_image(tempfile):
    logger.info(f"Compressing image at {tempfile}")
    try:
        max_size_kb = 500

        temp_path = tempfile.name
        file_name = os.path.basename(temp_path)
        if '.' not in file_name:
            logger.error(f"Invalid file name format: {file_name}")
            return None

        name, ext = os.path.splitext(file_name)
        ext = ext.lower().lstrip('.')  # 'jpg', 'jpeg', etc.
        # logger.info(f'\ntemp_path:{temp_path}\nfile_name: {file_name}\nname: {name}\next:{ext}')

        final_filename = secure_filename(f"{name}.jpg")
        final_filepath = os.path.join(Config.UPLOAD_DIR, final_filename)
        # logger.info(f'\nfinal_filename:{final_filename}\nfinal_filepath: {final_filepath}')

        img_format = 'JPEG' if ext in ['.jpg', '.jpeg'] else 'PNG'

        img = Image.open(temp_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')

        scale = 1.0
        while scale > 0.1:
            resized = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
            buffer = io.BytesIO()

            if img_format == 'JPEG':
                for quality in range(85, 10, -5):
                    buffer.seek(0)
                    buffer.truncate(0)
                    resized.save(buffer, format=img_format, quality=quality, optimize=True, exif=b'')
                    if buffer.tell() <= max_size_kb:
                        with open(final_filepath, 'wb') as f:
                            f.write(buffer.getvalue())
                        return final_filepath
            else:  # PNG
                resized.save(buffer, format=img_format, optimize=True)
                if buffer.tell() <= max_size_kb:
                    with open(final_filepath, 'wb') as f:
                        f.write(buffer.getvalue())
                    return final_filepath

            scale -= 0.1

        # Save last attempt even if not within size limit
        img.save(final_filepath, format='JPEG', optimize=True)
        logger.info(f"Compressed image saved to {final_filepath}")

        return final_filepath
    except Exception as e:
        logger.error(f"Failed to compress image at {tempfile}: {e}")
        return None

def generate_image_thumbnail(source_path, dest_path, size=(300, 300)):
    with Image.open(source_path) as img:
        img.thumbnail(size)
        img.save(dest_path, "JPEG")
def generate_pdf_thumbnail(source_path, dest_path):
    images = convert_from_path(source_path, first_page=1, last_page=1, size=(300, 300))
    images[0].save(dest_path, "JPEG")
def generate_text_thumbnail(source_path, dest_path, width=800, height=500):
    try:
        # Font settings
        font_path = 'assets/venus_cormier.otf'
        font_size = 24
        padding = 20
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            font = ImageFont.truetype("arial.ttf", font_size)

        # Read and prepare text
        with open(source_path, 'r', encoding='utf-8') as f:
            text = f.read()

        words = text.split()
        lines = []
        line = ""

        # Dummy draw to measure text
        dummy_img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(dummy_img)

        for word in words:
            test_line = line + " " + word if line else word
            if draw.textlength(test_line, font=font) < (width - 2 * padding):
                line = test_line
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)

        # Calculate image height dynamically
        line_height = font_size + 10
        img_height = padding * 2 + len(lines) * line_height

        image = Image.new("RGB", (width, img_height), "white")
        draw = ImageDraw.Draw(image)

        y = padding
        for line in lines:
            draw.text((padding, y), line, font=font, fill="black")
            y += line_height

        image.save(dest_path)
    except Exception as e:
        logger.error(f"generate_text_thumbnail error: {e}")
        return
def generate_thumbnail(file_path):
    logger.info(f"Generating thumbnail for {file_path}")
    try:
        thumbnail_uuid = uuid.uuid4().hex
        ext = file_path.lower()
        dest_path = os.path.join(Config.THUMBNAIL_DIR, f"{thumbnail_uuid}.jpg")

        if ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            generate_image_thumbnail(file_path, dest_path)
        elif ext.endswith('.pdf'):
            generate_pdf_thumbnail(file_path, dest_path)
        elif ext.endswith('.txt'):
            generate_text_thumbnail(file_path, dest_path)
        else:
            return None  # unsupported
        
        final_thumbnail_path = os.path.join(Config.THUMBNAIL_DIR, f"{thumbnail_uuid}.jpg")
        logger.info(f"Thumbnail created at {final_thumbnail_path}")
        
        return final_thumbnail_path
    except Exception as e:
        logger.error(f"Failed to create thumbnail for {file_path}: {e}")
        return None
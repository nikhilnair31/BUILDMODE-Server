# pre_process.py

import io
import os
import uuid
import tempfile
import logging
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PATTERN = rf'<tags>(.*?)<\/tags>'

def compress_image(file, upload_dir):
    file_uuid = uuid.uuid4().hex
    
    # Determine file extension safely
    if hasattr(file, 'filename'):
        ext = os.path.splitext(file.filename)[1].lower()
        filename = secure_filename(f"{file_uuid}{ext}")
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(temp_path)
    else:
        # Assume file is a file-like object (e.g., open("path", "rb"))
        ext = '.jpg'  # fallback extension, optionally infer from content
        filename = f"{file_uuid}{ext}"
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        with open(temp_path, "wb") as out_file:
            out_file.write(file.read())

    final_filename = secure_filename(f"{file_uuid}.jpg")
    final_filepath = os.path.join(upload_dir, final_filename)
    max_size_kb = 500

    img = Image.open(temp_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')

    img_format = 'JPEG' if ext in ['.jpg', '.jpeg'] else 'PNG'

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

def generate_image_thumbnail(source_path, dest_path, size=(300, 300)):
    with Image.open(source_path) as img:
        img.thumbnail(size)
        img.save(dest_path, "JPEG")
def generate_pdf_thumbnail(source_path, dest_path):
    images = convert_from_path(source_path, first_page=1, last_page=1, size=(300, 300))
    images[0].save(dest_path, "JPEG")
def generate_text_thumbnail(source_path, dest_path, width=300, height=300):
    try:
        font = ImageFont.load_default()
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        with open(source_path, 'r') as f:
            lines = f.readlines()[:10]
        
        y = 10
        for line in lines:
            draw.text((10, y), line.strip(), font=font, fill='black')
            y += 15

        image.save(dest_path)
    except Exception as e:
        print(f"Error: {e}")
        return
def generate_thumbnail(file_path, thumbnail_dir):
    try:
        thumbnail_uuid = uuid.uuid4().hex
        ext = file_path.lower()
        dest_path = os.path.join(thumbnail_dir, f"{thumbnail_uuid}.jpg")

        if ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            generate_image_thumbnail(file_path, dest_path)
        elif ext.endswith('.pdf'):
            generate_pdf_thumbnail(file_path, dest_path)
        elif ext.endswith('.txt'):
            generate_text_thumbnail(file_path, dest_path)
        else:
            return None  # unsupported
        
        final_thumbnail_path = os.path.join(thumbnail_dir, f"{thumbnail_uuid}.jpg")
        logger.info(f"Thumbnail created at {final_thumbnail_path}")
        
        return final_thumbnail_path
    except Exception as e:
        print(f"Failed to create thumbnail for {file_path}: {e}")
        return None
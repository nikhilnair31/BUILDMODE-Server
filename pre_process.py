# pre_process.py

import io
import os
import uuid
import tempfile
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path

PATTERN = rf'<tags>(.*?)<\/tags>'

def compress_image(file, upload_dir):
    file_uuid = uuid.uuid4().hex
    temp_ext = os.path.splitext(file.filename)[1]
    temp_path = os.path.join(tempfile.gettempdir(), secure_filename(f"{file_uuid}{temp_ext}"))
    file.save(temp_path)

    img = Image.open(temp_path).convert("RGB")
    buffer = BytesIO()

    max_size_kb = 500  # Target size in KB
    quality = 85  # Start with decent quality

    while True:
        buffer.seek(0)
        img.save(buffer, format="JPEG", quality=quality)
        size_kb = buffer.tell() / 1024
        if size_kb <= max_size_kb or quality <= 50:
            break
        quality -= 5

    buffer.seek(0)

    final_filename = secure_filename(f"{file_uuid}.jpg")
    final_filepath = os.path.join(upload_dir, final_filename)
    
    with open(final_filepath, 'wb') as f:
        f.write(buffer.getvalue())

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
        return f"thumbnails/{thumbnail_uuid}.jpg"
    except Exception as e:
        print(f"Failed to create thumbnail for {file_path}: {e}")
        return None
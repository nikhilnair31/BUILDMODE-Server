# pre_process.py

import io
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path

PATTERN = rf'<tags>(.*?)<\/tags>'

THUMBNAIL_DIR = './thumbnails'

def preprocess_image(file_path):
    img = Image.open(file_path).convert("RGB")
    buffer = io.BytesIO()

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

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    temp_file.write(buffer.getvalue())
    temp_file.close()

    return temp_file.name

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
def thumbnail_image(file_path, file_id):
    ext = file_path.lower()
    dest_path = os.path.join(THUMBNAIL_DIR, f"{file_id}.jpg")

    try:
        if ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            generate_image_thumbnail(file_path, dest_path)
        elif ext.endswith('.pdf'):
            generate_pdf_thumbnail(file_path, dest_path)
        elif ext.endswith('.txt'):
            generate_text_thumbnail(file_path, dest_path)
        else:
            return None  # unsupported
        return f"thumbnails/{file_id}.jpg"
    except Exception as e:
        print(f"Failed to create thumbnail for {file_path}: {e}")
        return None
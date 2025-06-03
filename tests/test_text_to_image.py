
import os
import uuid
import logging
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_text_thumbnail(source_path, dest_path, width=800, height=450):
    try:
        # Choose a basic font if not specified
        font_size = 24
        padding = 20
        font = ImageFont.truetype(
            font = 'assets/venus_cormier.otf' or "arial.ttf", 
            size = font_size
        )
        # Estimate height dynamicallyAdd commentMore actions
        lines = []
        draw = ImageDraw.Draw(Image.new("RGB", (width, 1000)))
        
        with open(source_path, 'r') as f:
            text = f.readlines()
        
        text = "".join(text)
        words = text.split()
        line = ""
        for word in words:
            if draw.textlength(line + " " + word, font=font) < width - 2 * padding:
                line += " " + word
            else:
                lines.append(line.strip())
                line = word
        lines.append(line.strip())
        
        height = padding * 2 + len(lines) * (font_size + 10)
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        
        y = padding
        for line in lines:
            draw.text((padding, y), line, font=font, fill="black")
            y += font_size + 10
        
        image.save(dest_path)
    except Exception as e:
        logger.error(f"generate_text_thumbnail error: {e}")
        return
def generate_thumbnail(file_path, thumbnail_dir):
    logger.info(f"Generating thumbnail for {file_path}")
    try:
        thumbnail_uuid = uuid.uuid4().hex
        ext = file_path.lower()
        dest_path = os.path.join(thumbnail_dir, f"{thumbnail_uuid}.jpg")

        if ext.endswith('.txt'):
            generate_text_thumbnail(file_path, dest_path)
        else:
            return None  # unsupported
        
        final_thumbnail_path = os.path.join(thumbnail_dir, f"{thumbnail_uuid}.jpg")
        logger.info(f"Thumbnail created at {final_thumbnail_path}")
        
        return final_thumbnail_path
    except Exception as e:
        logger.error(f"Failed to create thumbnail for {file_path}: {e}")
        return None
    
if __name__ == "__main__":
    generate_thumbnail(
        './uploads/1541ed115982429ab8aed5ac49ef4e68.txt',
        './'
    )
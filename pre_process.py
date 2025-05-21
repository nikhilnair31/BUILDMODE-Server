import io
import tempfile
from PIL import Image

PATTERN = rf'<tags>(.*?)<\/tags>'

def preprocess_image(file_path):
    img = Image.open(file_path).convert("RGB")
    buffer = io.BytesIO()

    quality = 85  # Start with decent quality

    while True:
        buffer.seek(0)
        img.save(buffer, format="JPEG", quality=quality)
        size_kb = buffer.tell() / 1024
        if size_kb <= 150 or quality <= 50:
            break
        quality -= 5

    buffer.seek(0)

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    temp_file.write(buffer.getvalue())
    temp_file.close()

    return temp_file.name
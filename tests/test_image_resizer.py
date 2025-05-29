import os
from PIL import Image
from io import BytesIO

UPLOADS_DIR = "uploads"
MAX_SIZE_BYTES = 512000  # 500 KB

def compress_image(input_path, output_path, file_ext):
    try:
        img = Image.open(input_path)

        # Convert to RGB to avoid mode issues (like RGBA or P)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        img_format = img.format or file_ext.replace('.', '').upper()

        if file_ext.lower() in ['.jpg', '.jpeg']:
            quality = 85
            scale = 1.0
            while scale > 0.1:
                new_size = (int(img.width * scale), int(img.height * scale))
                resized_img = img.resize(new_size, Image.LANCZOS)
                temp_quality = quality
                while temp_quality > 10:
                    buffer = BytesIO()
                    resized_img.save(
                        buffer,
                        format=img_format,
                        quality=temp_quality,
                        optimize=True,
                        exif=b''  # Strip metadata
                    )
                    if buffer.tell() <= MAX_SIZE_BYTES:
                        with open(output_path, 'wb') as f:
                            f.write(buffer.getvalue())
                        return True
                    temp_quality -= 5
                scale -= 0.1

        elif file_ext.lower() == '.png':
            # Try reducing size
            scale = 1.0
            while scale > 0.1:
                new_size = (int(img.width * scale), int(img.height * scale))
                resized_img = img.resize(new_size, Image.LANCZOS)
                buffer = BytesIO()
                resized_img.save(buffer, format='PNG', optimize=True)
                if buffer.tell() <= MAX_SIZE_BYTES:
                    with open(output_path, 'wb') as f:
                        f.write(buffer.getvalue())
                    return True
                scale -= 0.1

        print(f"[!] Could not reduce {input_path} under 500 KB.")
        return False
    except Exception as e:
        print(f"[!] Error processing {input_path}: {e}")
        return False

def resize_large_images():
    for root, _, files in os.walk(UPLOADS_DIR):
        for file in files:
            file_ext = os.path.splitext(file)[1].lower()
            if file_ext not in ['.jpg', '.jpeg', '.png']:
                continue

            path = os.path.join(root, file)
            size = os.path.getsize(path)
            if size > MAX_SIZE_BYTES:
                print(f"[+] Resizing: {file} ({size} bytes)")
                compress_image(path, path, file_ext)

if __name__ == "__main__":
    resize_large_images()

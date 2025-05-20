import re
import io
import json
import base64
import tempfile
import datetime
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

def preprocess_image2(image_objectkey, image_filepath, db_filepath):
    # Set vars
    timestamp_str = str(datetime.datetime.now())
    PROCESS_SYSTEM_PROMPT = """
        Extract a long and comprehensive list of keywords to describe the image provided. These keywords will be used for semantic search eventually. Extract things like themes, dominant/accent colors, moods along with more descriptive terms. If possible determine the app the screenshot was taken in as well. Ignore phone status information. Only output as shown below
        <tags>
        keyword1, keyword2, ...
        </tags>
    """
    
    try:
        # Read image file and convert to base64
        with open(image_filepath, "rb") as image_file:
            image_bytes = image_file.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        # Calling LLM
        llm_response = call_llm_api(PROCESS_SYSTEM_PROMPT, image_b64)
        
        # Process LLM response
        analysis_raw_json_str = json.dumps(llm_response)
        analysis_raw_text = llm_response['candidates'][0]['content']['parts'][0]['text']
        matches = re.findall(PATTERN, analysis_raw_text, re.DOTALL)
        if matches:
            analysis_raw_text = matches[0].strip().split(', ')
            analysis_raw_text = ','.join(analysis_raw_text)
        print(f"analysis_raw_text: {analysis_raw_text}")

        # Calling Vec
        vec_response = call_vec_api(analysis_raw_text)
        
        # Insert the data
        insert_ss_data = (
            image_objectkey,
            analysis_raw_json_str,
            analysis_raw_text,
            timestamp_str
        )
        insert_vec_data = (
            image_objectkey,
            vec_response
        )
        insert_to_screenshots_tbl(db_filepath, insert_ss_data)
        insert_to_vec_tbl(db_filepath, insert_vec_data)
        
        print("Process completed successfully")
    
    except Exception as e:
        raise Exception(f"Process failed with error: {e}")
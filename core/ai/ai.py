# ai.py

import os
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LLM_PROVIDER = "gemini"
VEC_PROVIDER = "gemini"

def call_llm_api(sysprompt, text_or_images):
    print(f"\nLLM...")

    if LLM_PROVIDER == "gemini":
        if isinstance(text_or_images, list):
            return call_gemini_with_images(sysprompt, text_or_images)
        elif isinstance(text_or_images, str):
            return call_gemini_with_text(sysprompt, text_or_images)
        
    return ""
def call_gemini_with_images(sysprompt, image_b64_list):
    print(f"Calling Gemini...\n")

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    MODEL_ID = "gemini-2.0-flash"

    client = genai.Client(api_key=GEMINI_API_KEY)
    parts = [
        types.Part.from_bytes(data=b64, mime_type="image/jpeg") for b64 in image_b64_list
    ]
    response = client.models.generate_content(
        model=MODEL_ID,
        config=types.GenerateContentConfig(
            system_instruction=sysprompt,
            temperature=1.0
        ),
        contents=parts
    )
    # print(f"response: {response}\n")
    # print(f"response: {response[:10]}\n")

    content_text = response.text
    
    return content_text
def call_gemini_with_text(sysprompt, text):
    print(f"Calling Gemini with text...\n")

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    MODEL_ID = "gemini-2.0-flash"

    client = genai.Client(api_key=GEMINI_API_KEY)
    response_schema = genai.types.Schema(
        type=genai.types.Type.OBJECT,
        required=["urls"],
        properties={
            "urls": genai.types.Schema(
                type=genai.types.Type.ARRAY,
                items=genai.types.Schema(
                    type=genai.types.Type.STRING
                )
            )
        }
    )
    response = client.models.generate_content(
        model=MODEL_ID,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            system_instruction=sysprompt,
            temperature=1.0
        ),
        contents=[text]
    )

    return response.text

def call_vec_api(query_text):
    print(f"Vec...")

    if VEC_PROVIDER == "gemini":
        response_json = get_gemini_embedding(query_text)
        return response_json
        
    return []
def get_gemini_embedding(text, task_type="SEMANTIC_SIMILARITY"):
    print(f"Getting Gemini embedding...\n")
    
    try:
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
        MODEL_ID = "text-embedding-004"

        client = genai.Client(api_key = GEMINI_API_KEY)
        response = client.models.embed_content(
            model=MODEL_ID,
            contents=text,
            config=types.EmbedContentConfig(task_type=task_type)
        )
        # print(f"response: {response[:10]}\n")
        # print(f"len(response.embeddings[0].values): {len(response.embeddings[0].values)}\n")
        # 768

        embedding = response.embeddings[0].values
        return embedding
            
    except Exception as e:
        print(f"Error getting Gemini embedding: {e}")
        return []
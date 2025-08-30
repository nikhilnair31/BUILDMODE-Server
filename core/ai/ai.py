# ai.py

import os
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------- GENERATE ------------------------------------
 
def call_llm_api(sys_prompt, image_list):
    print(f"\nLLM...")

    return call_gemini_with_images(sys_prompt, image_list)

def call_gemini_with_images(sys_prompt, image_b64_list):
    print(f"Calling Gemini generate...\n")

    try:
        client = genai.Client(api_key = os.environ.get("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=0.2
            ),
            contents=[
                types.Part.from_bytes(data=b64, mime_type="image/jpeg") for b64 in image_b64_list
            ]
        )

        return response.text
            
    except Exception as e:
        print(f"Error getting Gemini generate: {e}")
        return ""

# ---------------------------------- EMBEDDINGS ----------------------------------
 
def call_vec_api(query_text, task_type):
    print(f"Vec...")

    response_json = get_gemini_embedding(query_text, task_type)
    return response_json

def get_gemini_embedding(text, task_type):
    print(f"Getting Gemini embedding...\n")
    
    try:
        client = genai.Client(api_key = os.environ.get("GEMINI_API_KEY"))
        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=768
            )
        )

        embedding = response.embeddings[0].values
        return embedding
            
    except Exception as e:
        print(f"Error getting Gemini embedding: {e}")
        return []
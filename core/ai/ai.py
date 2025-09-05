# ai.py

import os
import logging
from exa_py import Exa
from google import genai
from google.genai import types
from dotenv import load_dotenv
from core.utils.config import Config, Content

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------- GENERATE ------------------------------------
 
def call_llm_api(image_list, sys_prompt=Config.IMAGE_CONTENT_EXTRACTION_SYSTEM_PROMPT, temp=0.2):
    print(f"\nLLM...")

    return call_gemini_with_images(image_list, sys_prompt, temp)

def call_gemini_with_images(image_list, sys_prompt, temp):
    print(f"Calling Gemini generate...\n")

    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=b64, mime_type="image/jpeg") for b64 in image_list
            ],
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=temp,
                response_schema=Content,
                response_mime_type="application/json",
                thinking_config = types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
        )

        return response.text
            
    except Exception as e:
        print(f"Error getting Gemini generate: {e}")
        return ""

def call_gemini_with_text(sys_prompt, usr_prompt, temp = 0.2):
    print(f"Calling Gemini generate...\n")

    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=usr_prompt,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=temp,
                thinking_config = types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
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
        client = genai.Client(
            api_key = os.environ.get("GEMINI_API_KEY")
        )
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

# ---------------------------------- SEARCH ----------------------------------

def get_exa_search(text):
    print(f"Getting Exa AI search...\n")
    
    try:
        exa = Exa(
            api_key=os.environ.get("EXA_AI_API_KEY")
        )
        result = exa.search_and_contents(
            text,
            type = "auto",
            num_results = 3,
            start_published_date = "2025-08-29T04:00:00.000Z",
            end_published_date = "2025-09-06T03:59:59.999Z",
            livecrawl_timeout = 1000,
            text = {
                "max_characters": 512
            },
            context = True,
            summary = True
        )

        out = result.results
        return out
            
    except Exception as e:
        print(f"Error getting Exa AI search: {e}")
        return []

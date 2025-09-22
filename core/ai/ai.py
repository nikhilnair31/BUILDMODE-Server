# ai.py

import os, logging
from typing import List
from exa_py import Exa
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import requests
from core.utils.config import Config
from core.utils.timing import timed_route

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Content(BaseModel):
    app_name: str
    engagement_counts: list[str]
    account_identifiers: list[str]
    links: list[str]
    full_ocr: str
    keywords: List[str] = Field(default_factory=list, max_items=25)
    accent_colors: list[str]
    themes: list[str]
    moods: list[str]

# ---------------------------------- GENERATE ------------------------------------
 
@timed_route("call_llm_api")
def call_llm_api(image_b64, sys_prompt=Config.IMAGE_CONTENT_EXTRACTION_SYSTEM_PROMPT, temp=0.2):
    print(f"LLM...")

    return call_gemini_with_images(image_b64, sys_prompt, temp)

@timed_route("call_gemini_with_images")
def call_gemini_with_images(image_b64, sys_prompt, temp):
    print(f"Calling Gemini generate...")

    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=image_b64, mime_type="image/jpeg")
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

@timed_route("call_gemini_with_text")
def call_gemini_with_text(sys_prompt, usr_prompt, temp = 0.2):
    print(f"Calling Gemini generate...")

    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
        response = client.models.generate_content(
            model="gemini-2.0-flash",
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
 
@timed_route("call_vec_api")
def call_vec_api(query_text, task_type):
    print(f"Vec...")

    response_json = get_gemini_embedding(query_text, task_type)
    return response_json

@timed_route("get_gemini_embedding")
def get_gemini_embedding(text, task_type):
    print(f"Getting Gemini embedding...")
    
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

@timed_route("get_exa_search")
def get_exa_search(query: str, inc_domains = None):
    print(f"Getting Exa AI search...")
    
    try:
        token = os.environ.get("EXA_AI_API_KEY")
        if not token:
            raise RuntimeError("EXA_AI_API_KEY not set")
        
        exa = Exa(api_key=token)
        
        kwargs = {
            "query": query,
            "type": "auto",
            "num_results": 25,
        }
        if inc_domains:  # only add if user has interacted
            kwargs["include_domains"] = inc_domains
        
        result = exa.search_and_contents(**kwargs)

        return result.results
            
    except Exception as e:
        print(f"Error getting Exa AI search: {e}")
        return []

@timed_route("get_brave_search")
def get_brave_search(query: str, inc_domains = None):
    print(f"Getting Brave AI search...")
    
    try:
        token = os.environ.get("BRAVE_AI_API_KEY")
        if not token:
            raise RuntimeError("BRAVE_AI_API_KEY not set")

        params = {"q": query}
        if inc_domains:
            params["include_domains"] = ",".join(inc_domains)

        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json",
                     "x-subscription-token": token},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("web", {}).get("results", [])
            
    except Exception as e:
        print(f"Error getting Brave AI search: {e}")
        return []

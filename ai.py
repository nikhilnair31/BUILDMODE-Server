import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = "gemini"
VEC_PROVIDER = "gemini"

def call_llm_api(sysprompt, image_b64_list):
    print(f"\nLLM...")

    if LLM_PROVIDER == "gemini":
        response_json = call_gemini(sysprompt, image_b64_list)
        return response_json
        
    return ""
def call_gemini(sysprompt, image_b64_list):
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
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from core.processing.background import encode_image_to_base64
from core.utils.config import Config, Content

load_dotenv()

# HexColor = constr(pattern=r"^#(?:[0-9a-fA-F]{6})$")

file_path = "/root/projects/BUILDMODE-Server/uploads/0a8e38e2493743538499dfa6726f5417.jpg"

def call_gemini1(sys_prompt, image_list, temp=1):
    print(f"Calling Gemini generate...\n")

    try:
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
        MODEL_ID = "gemini-2.0-flash"

        client = genai.Client(api_key=GEMINI_API_KEY)
        parts = [
            types.Part.from_bytes(data=b64, mime_type="image/jpeg") for b64 in image_list
        ]
        response = client.models.generate_content(
            model=MODEL_ID,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=temp
            ),
            contents=parts
        )
        # print(f"response: {response}\n")
        # print(f"response: {response[:10]}\n")

        content_text = response.text
        
        return content_text
            
    except Exception as e:
        print(f"Error getting Gemini generate: {e}")
        return ""
def call_gemini3(sys_prompt, image_list, temp=1):
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
                temperature=temp,
                thinking_config = types.ThinkingConfig(
                    thinking_budget=0,
                ),
                response_mime_type="application/json",
                response_schema=Content,
                system_instruction=sys_prompt,
            ),
        )
        # print(f"response: {response}\n")
        # print(f"response: {response[:10]}\n")

        content_text = response.text
        
        return content_text
            
    except Exception as e:
        print(f"Error getting Gemini generate: {e}")
        return ""

TAG_PROMPT_0 = Config.IMAGE_CONTENT_EXTRACTION_SYSTEM_PROMPT
TAG_PROMPT_1 = """
    Extract a long and comprehensive list of keywords to describe the image provided. 
    These keywords will be used for semantic search eventually. 
    Extract things like themes, dominant/accent colors, moods along with more descriptive terms. 
    If possible determine the app the screenshot was taken in as well. 
    Ignore phone status information. 
    Only output as shown below
    <tags>
    keyword1, keyword2, ...
    </tags>
"""
TAG_PROMPT_2 = """
    Extract a long and comprehensive list of comma separated keywords to describe the image provided. 
    These keywords will be used for semantic search. 
    Extract things like themes, dominant/accent colors, moods, social media site/app name, engagement metrics; along with more descriptive terms.
    Ignore phone status information.
"""
TAG_PROMPT_3 = """
    Extract a long and comprehensive list of comma separated keywords to describe the image provided. 
    These keywords will be used for semantic search. 
    
    Extract things like shown:
    App Name: app.
    Engagement Counts: 1.2K likes, 60 comments, 3M views, 200 bookmarks, 6 shares, 12 retweets, 12K upvotes etc.
    Account Identifiers; @account1, @account2, etc.
    Links: link1, link2, etc.
    Full OCR: content.
    Keywords: keyword1, keyword2, etc.
    Accent Colors: color1, color2, etc.
    Themes: theme1, theme2, etc.
    Moods: color1, color2, etc.

    Ignore phone status information.
"""

image_base64 = [encode_image_to_base64(file_path)]

# tags_0 = call_gemini1(sys_prompt=TAG_PROMPT_0, image_list=image_base64)
# print(f"tags_0:\n{tags_0}")

# tags_1 = call_gemini1(sys_prompt=TAG_PROMPT_1, image_list=image_base64)
# print(f"tags_1:\n{tags_1}")

# tags_2 = call_gemini1(sys_prompt=TAG_PROMPT_2, image_list=image_base64)
# print(f"tags_2:\n{tags_2}")

tags_3 = call_gemini3(sys_prompt=TAG_PROMPT_3, image_list=image_base64, temp=0.2)
print(f"tags_3:\n{tags_3}")
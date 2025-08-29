from core.ai.ai import call_llm_api
from core.processing.background import encode_image_to_base64
from core.utils.config import Config

file_path = "/root/projects/BUILDMODE-Server/uploads/0a8e38e2493743538499dfa6726f5417.jpg"

TAG_PROMPT_0 = Config.IMAGE_PREPROCESS_SYSTEM_PROMPT
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
    Keywords: keyword1, keyword2, etc.
    Accent Colors: color1, color2, etc.
    Themes: theme1, theme2, etc.
    Moods: color1, color2, etc.

    Ignore phone status information.
"""

image_base64 = [encode_image_to_base64(file_path)]

# tags_0 = call_llm_api(sys_prompt=TAG_PROMPT_0, image_list=image_base64)
# print(f"tags_0:\n{tags_0}")

# tags_1 = call_llm_api(sys_prompt=TAG_PROMPT_1, image_list=image_base64)
# print(f"tags_1:\n{tags_1}")

# tags_2 = call_llm_api(sys_prompt=TAG_PROMPT_2, image_list=image_base64)
# print(f"tags_2:\n{tags_2}")

tags_3 = call_llm_api(sys_prompt=TAG_PROMPT_3, image_list=image_base64)
print(f"tags_3:\n{tags_3}")
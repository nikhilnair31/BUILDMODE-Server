import json
import os
from exa_py import Exa
from dotenv import load_dotenv

load_dotenv()

EXA_AI_API_KEY = os.environ.get("EXA_AI_API_KEY")

exa = Exa(
    api_key=EXA_AI_API_KEY
)

result = exa.search_and_contents(
    "blog posts about AI",
    type = "auto",
    num_results = 2,
    start_published_date = "2025-08-29T04:00:00.000Z",
    end_published_date = "2025-09-06T03:59:59.999Z",
    livecrawl_timeout = 1000,
    text = {
        "max_characters": 512
    },
    context = True,
    summary = {

    }
)
print("result")
print(result)
print("-"*50)
for idx, item in enumerate(result.results):
    print(f"{idx}: {item.id}")
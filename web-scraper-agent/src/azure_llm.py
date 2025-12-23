# src/azure_llm.py  (LOADS .env AT IMPORT TIME)
import os
from dotenv import load_dotenv
load_dotenv()  # MUST be before openai import

import openai
import json
from utils.token_tracker import TokenTracker

# Now safe to create client
client = openai.AsyncAzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version="2024-06-01"
)
deployment = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-mini")
tk = TokenTracker()  # SINGLETON

async def ask_llm(system: str, user: str, temp: float = 0.2) -> str:
    tk.count(system + user)
    resp = await client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        temperature=temp,
        max_tokens=1000
    )
    out = resp.choices[0].message.content
    tk.count(out)
    return out
# src/azure_llm.py  (LOADS .env AT IMPORT TIME)
import os
from dotenv import load_dotenv
load_dotenv()  # MUST be before openai import

import openai
import json
from utils.token_tracker import TokenTracker
from loguru import logger

# Lazy-init client to avoid side-effects at import time
_client = None
deployment = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-mini")
tk = TokenTracker()  # SINGLETON

def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        if not api_key or not endpoint:
            logger.warning("Azure LLM credentials not fully set (AZURE_OPENAI_API_KEY/AZURE_OPENAI_ENDPOINT)")
        _client = openai.AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version="2024-06-01"
        )
    return _client

async def ask_llm(system: str, user: str, temp: float = 0.2) -> str:
    try:
        # Track tokens for diagnostics
        tk.count(system + user)
        logger.debug("LLM call: model={} temp={} system_len={} user_len={}", deployment, temp, len(system), len(user))

        client = _get_client()

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
        logger.debug("LLM response length={}", len(out) if out else 0)
        return out
    except Exception as e:
        logger.exception("LLM call failed: {}", e)
        raise
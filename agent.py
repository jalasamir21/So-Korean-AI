"""
agent.py

Calls an LLM to extract product fields from scraped page text. The
model never sees or produces pricing math — it only returns raw facts
about the product, which calculator.py then turns into a total.
"""

import json
import os

from dotenv import load_dotenv
from groq import Groq

from prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
REQUIRED_FIELDS = {"productName", "price", "weight"}

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set — copy .env.example to .env and fill it in.")
        _client = Groq(api_key=api_key)
    return _client


class ExtractionError(Exception):
    pass


def extract_product_fields(store: str, page_text: str) -> dict:
    if not page_text.strip():
        raise ExtractionError("No readable content was found on that page.")

    response = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": build_extraction_prompt(store, page_text)},
        ],
    )

    raw = (response.choices[0].message.content or "").strip()
    raw = _strip_code_fence(raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Model did not return valid JSON: {raw[:200]}") from e

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        raise ExtractionError(f"Extraction is missing fields: {sorted(missing)}")

    data.setdefault("timeDeal", False)
    data.setdefault("eligibleForCode", False)
    return data


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: -3]
    return text.strip()
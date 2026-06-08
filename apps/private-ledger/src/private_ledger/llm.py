# b17: 47128  ΔΣ=42
import json
from datetime import date
from typing import AsyncGenerator

import httpx

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "yggdrasil:v9"

_PARSE_SYSTEM = """\
You are a personal finance parser. Parse user input into a JSON transaction.
Return ONLY valid JSON with no explanation. Fields:
  date        – YYYY-MM-DD string (infer from context; default today)
  amount      – float, negative for expenses/payments, positive for income/deposits
  description – concise title-case label, 2-5 words
  category    – exactly one of: Food & Dining, Housing, Transportation, Utilities,
                Entertainment, Healthcare, Shopping, Income, Other

If you cannot parse the input, return: {"error": "cannot parse"}"""

_INSIGHTS_SYSTEM = """\
You are a personal finance advisor. You have access to the user's recent transactions
and budget data. Answer their question concisely, specifically, and actionably.
Keep your response under 200 words. Do not pad with generic advice."""


async def parse_transaction(text: str, today: str | None = None, model: str = DEFAULT_MODEL) -> dict:
    if today is None:
        today = date.today().isoformat()
    prompt = f"Today is {today}.\n\nParse: {text}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "system": _PARSE_SYSTEM, "prompt": prompt,
                  "stream": False, "format": "json"},
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "{}")
        return json.loads(raw)


async def stream_insights(
    question: str,
    tx_text: str,
    budget_text: str,
    model: str = DEFAULT_MODEL,
) -> AsyncGenerator[str, None]:
    prompt = (
        f"Recent transactions:\n{tx_text}\n\n"
        f"Budget summary:\n{budget_text}\n\n"
        f"Question: {question}"
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "system": _INSIGHTS_SYSTEM,
                  "prompt": prompt, "stream": True},
        ) as resp:
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if token := chunk.get("response"):
                        yield token
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    pass

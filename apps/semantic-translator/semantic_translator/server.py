"""FastAPI web server for semantic-translator."""
from __future__ import annotations

import json
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Semantic Translator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_WEB_DIR = pathlib.Path(__file__).parent.parent / "web"


class SearchRequest(BaseModel):
    text: str
    limit: int = 5


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    html = _WEB_DIR / "index.html"
    if html.exists():
        return html.read_text(encoding="utf-8")
    return "<h1>Semantic Translator</h1><p>No web/index.html found.</p>"


@app.post("/search")
async def search_endpoint(req: SearchRequest) -> dict:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")
    from .search import search
    try:
        results = search(req.text.strip(), limit=max(1, min(req.limit, 20)))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"query": req.text, "count": len(results), "results": results}


@app.get("/corpus/stats")
async def corpus_stats() -> dict:
    corpus = pathlib.Path("data/corpus.jsonl")
    if not corpus.exists():
        return {"segments": 0, "lessons": 0, "languages": {}}
    lessons: set[str] = set()
    langs: dict[str, int] = {}
    count = 0
    with open(corpus, encoding="utf-8") as f:
        for line in f:
            seg = json.loads(line)
            lessons.add(seg["lesson"])
            langs[seg["lang"]] = langs.get(seg["lang"], 0) + 1
            count += 1
    return {"segments": count, "lessons": len(lessons), "languages": langs}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

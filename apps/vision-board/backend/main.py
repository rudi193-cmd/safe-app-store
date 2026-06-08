#!/usr/bin/env python3
"""
Vision Board Backend — FastAPI + SAP Bridge

Provides image classification via Ollama vision model.
Falls back gracefully if Ollama unavailable.

AUTHOR: Kartikeya
PORT: 8420
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import base64
import io
import os
from pathlib import Path

from vision_processor import (
    classify_image_ollama,
    classify_image_batch,
    check_ollama_vision,
    CATEGORY_MAP,
    CATEGORY_COLORS,
)

app = FastAPI(
    title="Vision Board API",
    description="Image classification via Ollama vision",
    version="1.0.0",
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === MODELS ===

class ClassifyRequest(BaseModel):
    image_base64: str
    filename: Optional[str] = "image.jpg"


class ClassifyResponse(BaseModel):
    category: str
    label: str
    confidence: int
    description: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    ollama_available: bool
    vision_model: Optional[str] = None


class CategoryInfo(BaseModel):
    name: str
    color: str
    keywords: List[str]


# === ENDPOINTS ===

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Check if backend and Ollama are available."""
    ollama_ok, model_name = check_ollama_vision()
    return HealthResponse(
        status="ok",
        ollama_available=ollama_ok,
        vision_model=model_name if ollama_ok else None,
    )


@app.get("/api/categories", response_model=List[CategoryInfo])
async def get_categories():
    """Get available categories with colors and keywords."""
    categories = []

    # Group keywords by category
    category_keywords = {}
    for keyword, category in CATEGORY_MAP.items():
        if category not in category_keywords:
            category_keywords[category] = []
        category_keywords[category].append(keyword)

    for category, color in CATEGORY_COLORS.items():
        categories.append(CategoryInfo(
            name=category,
            color=color,
            keywords=category_keywords.get(category, [])[:10],  # Limit preview
        ))

    return categories


@app.post("/api/classify", response_model=ClassifyResponse)
async def classify_image(request: ClassifyRequest):
    """
    Classify a single image using Ollama vision.

    Accepts base64-encoded image data.
    Returns category, label, and confidence.
    """
    try:
        # Decode base64
        image_data = base64.b64decode(request.image_base64)

        # Classify via Ollama
        result = await classify_image_ollama(image_data, request.filename)

        return ClassifyResponse(
            category=result["category"],
            label=result["label"],
            confidence=result["confidence"],
            description=result.get("description"),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/classify/upload", response_model=ClassifyResponse)
async def classify_upload(file: UploadFile = File(...)):
    """
    Classify an uploaded image file.

    Alternative to base64 for direct file uploads.
    """
    try:
        contents = await file.read()
        result = await classify_image_ollama(contents, file.filename)

        return ClassifyResponse(
            category=result["category"],
            label=result["label"],
            confidence=result["confidence"],
            description=result.get("description"),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/classify/batch")
async def classify_batch(files: List[UploadFile] = File(...)):
    """
    Classify multiple images in batch.

    Returns list of classifications.
    """
    try:
        images = []
        for file in files:
            contents = await file.read()
            images.append({
                "data": contents,
                "filename": file.filename,
            })

        results = await classify_image_batch(images)

        return {
            "results": [
                ClassifyResponse(
                    category=r["category"],
                    label=r["label"],
                    confidence=r["confidence"],
                    description=r.get("description"),
                ).dict()
                for r in results
            ],
            "total": len(results),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === RUN ===

if __name__ == "__main__":
    import uvicorn
    print("Starting Vision Board API on port 8420...")
    uvicorn.run(app, host="0.0.0.0", port=8420)

#!/usr/bin/env python3
"""
Vision Processor — Ollama Vision Integration

Uses llama3.2-vision for image classification.
Maps descriptions to vision board categories.

AUTHOR: Kartikeya
"""

import requests
import base64
import re
import asyncio
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

# === CONFIG ===

OLLAMA_URL = "http://localhost:11434"
VISION_MODEL = "llama3.2-vision:latest"
FALLBACK_MODEL = "llava:latest"  # Alternative if primary not available

# === CATEGORY MAPPING ===

CATEGORY_COLORS = {
    "Personal": "#ff6b9d",
    "Travel": "#00d2ff",
    "Career": "#00ff9d",
    "Wealth": "#ffd700",
    "Fitness": "#ff6b35",
    "Creative": "#bd00ff",
    "Home": "#7dd87d",
    "Food": "#ffb347",
    "Relationships": "#ff69b4",
    "Inspiration": "#666666",
}

# Keywords that map to categories (from vision descriptions)
CATEGORY_MAP = {
    # Personal
    "cat": "Personal", "dog": "Personal", "pet": "Personal", "puppy": "Personal",
    "kitten": "Personal", "family": "Personal", "child": "Personal", "baby": "Personal",
    "portrait": "Personal", "selfie": "Personal",

    # Travel
    "beach": "Travel", "ocean": "Travel", "sea": "Travel", "mountain": "Travel",
    "landscape": "Travel", "sunset": "Travel", "sunrise": "Travel", "lake": "Travel",
    "forest": "Travel", "nature": "Travel", "vacation": "Travel", "travel": "Travel",
    "temple": "Travel", "church": "Travel", "monument": "Travel", "landmark": "Travel",
    "city": "Travel", "skyline": "Travel", "architecture": "Travel", "building": "Travel",
    "bridge": "Travel", "tower": "Travel", "castle": "Travel", "palace": "Travel",

    # Home
    "room": "Home", "interior": "Home", "furniture": "Home", "kitchen": "Home",
    "bedroom": "Home", "living room": "Home", "bathroom": "Home", "garden": "Home",
    "plant": "Home", "flower": "Home", "couch": "Home", "sofa": "Home",
    "table": "Home", "chair": "Home", "lamp": "Home", "decor": "Home",

    # Food
    "food": "Food", "meal": "Food", "dish": "Food", "plate": "Food",
    "restaurant": "Food", "cooking": "Food", "kitchen": "Food", "chef": "Food",
    "fruit": "Food", "vegetable": "Food", "dessert": "Food", "cake": "Food",
    "coffee": "Food", "drink": "Food", "wine": "Food", "beer": "Food",
    "pizza": "Food", "burger": "Food", "sushi": "Food", "salad": "Food",

    # Fitness
    "gym": "Fitness", "workout": "Fitness", "exercise": "Fitness", "fitness": "Fitness",
    "running": "Fitness", "yoga": "Fitness", "sport": "Fitness", "athlete": "Fitness",
    "bicycle": "Fitness", "bike": "Fitness", "swimming": "Fitness", "hiking": "Fitness",
    "weight": "Fitness", "muscle": "Fitness", "training": "Fitness",

    # Career
    "office": "Career", "desk": "Career", "computer": "Career", "laptop": "Career",
    "work": "Career", "business": "Career", "meeting": "Career", "presentation": "Career",
    "professional": "Career", "suit": "Career", "corporate": "Career",

    # Wealth
    "car": "Wealth", "luxury": "Wealth", "expensive": "Wealth", "rich": "Wealth",
    "yacht": "Wealth", "mansion": "Wealth", "jewelry": "Wealth", "watch": "Wealth",
    "sports car": "Wealth", "villa": "Wealth", "penthouse": "Wealth",

    # Creative
    "art": "Creative", "painting": "Creative", "drawing": "Creative", "music": "Creative",
    "guitar": "Creative", "piano": "Creative", "camera": "Creative", "photography": "Creative",
    "creative": "Creative", "design": "Creative", "craft": "Creative", "studio": "Creative",

    # Relationships
    "couple": "Relationships", "wedding": "Relationships", "love": "Relationships",
    "romantic": "Relationships", "date": "Relationships", "friends": "Relationships",
    "party": "Relationships", "celebration": "Relationships", "gathering": "Relationships",
}

DEFAULT_CATEGORY = "Inspiration"

# Thread pool for concurrent processing
executor = ThreadPoolExecutor(max_workers=4)


def check_ollama_vision() -> Tuple[bool, Optional[str]]:
    """Check if Ollama is available with a vision model."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code != 200:
            return False, None

        models = r.json().get("models", [])
        model_names = [m["name"] for m in models]

        # Check for vision models
        if VISION_MODEL in model_names or VISION_MODEL.split(":")[0] in [m.split(":")[0] for m in model_names]:
            return True, VISION_MODEL
        if FALLBACK_MODEL in model_names or FALLBACK_MODEL.split(":")[0] in [m.split(":")[0] for m in model_names]:
            return True, FALLBACK_MODEL

        # Check for any vision-capable model
        for name in model_names:
            if "vision" in name.lower() or "llava" in name.lower():
                return True, name

        return False, None

    except Exception:
        return False, None


def _describe_image_sync(image_data: bytes, model: str) -> str:
    """
    Synchronous image description via Ollama.

    Returns a text description of the image.
    """
    # Encode image as base64
    image_b64 = base64.b64encode(image_data).decode("utf-8")

    prompt = """Describe this image in one sentence. Focus on:
- Main subject (person, animal, object, scene)
- Setting/environment
- Any notable objects or activities

Be concise and factual."""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }

    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json=payload,
        timeout=60,
    )

    if r.status_code != 200:
        raise Exception(f"Ollama returned {r.status_code}")

    return r.json().get("response", "")


def _map_description_to_category(description: str) -> Tuple[str, int]:
    """
    Map a text description to a category.

    Returns (category, confidence).
    """
    description_lower = description.lower()

    # Score each category based on keyword matches
    scores = {}
    for keyword, category in CATEGORY_MAP.items():
        if keyword in description_lower:
            scores[category] = scores.get(category, 0) + 1

    if not scores:
        return DEFAULT_CATEGORY, 50

    # Get highest scoring category
    best_category = max(scores, key=scores.get)

    # Confidence based on number of matches
    match_count = scores[best_category]
    confidence = min(95, 60 + match_count * 10)

    return best_category, confidence


async def classify_image_ollama(image_data: bytes, filename: str = "image.jpg") -> Dict:
    """
    Classify an image using Ollama vision model.

    Returns dict with category, label, confidence, description.
    """
    # Check if Ollama vision is available
    ollama_ok, model = check_ollama_vision()

    if not ollama_ok:
        # Return default if no vision model
        return {
            "category": DEFAULT_CATEGORY,
            "label": "No vision model available",
            "confidence": 0,
            "description": "Ollama vision model not found. Install with: ollama pull llama3.2-vision",
        }

    try:
        # Run sync function in thread pool
        loop = asyncio.get_event_loop()
        description = await loop.run_in_executor(
            executor,
            _describe_image_sync,
            image_data,
            model,
        )

        # Map to category
        category, confidence = _map_description_to_category(description)

        # Extract a short label from the description
        label = description.split(".")[0][:50] if description else filename

        return {
            "category": category,
            "label": label,
            "confidence": confidence,
            "description": description,
        }

    except Exception as e:
        return {
            "category": DEFAULT_CATEGORY,
            "label": f"Error: {str(e)[:30]}",
            "confidence": 0,
            "description": str(e),
        }


async def classify_image_batch(images: List[Dict]) -> List[Dict]:
    """
    Classify multiple images concurrently.

    Each image dict should have 'data' (bytes) and 'filename'.
    """
    tasks = [
        classify_image_ollama(img["data"], img.get("filename", "image.jpg"))
        for img in images
    ]

    results = await asyncio.gather(*tasks)

    # Add filenames to results
    for i, result in enumerate(results):
        result["filename"] = images[i].get("filename", f"image_{i}.jpg")

    return results


# === CLI TEST ===

if __name__ == "__main__":
    import sys

    print("Vision Processor Test")
    print("=" * 40)

    # Check Ollama
    ok, model = check_ollama_vision()
    print(f"Ollama available: {ok}")
    print(f"Vision model: {model}")

    if len(sys.argv) > 1:
        # Test with provided image
        image_path = sys.argv[1]
        print(f"\nTesting with: {image_path}")

        with open(image_path, "rb") as f:
            image_data = f.read()

        import asyncio
        result = asyncio.run(classify_image_ollama(image_data, image_path))

        print(f"Category: {result['category']}")
        print(f"Label: {result['label']}")
        print(f"Confidence: {result['confidence']}%")
        print(f"Description: {result['description']}")

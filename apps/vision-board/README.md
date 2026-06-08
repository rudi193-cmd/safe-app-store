# Vision Board

AI-powered goal visualization. 96% client-side, 4% cloud.

## What It Does

Drop images. AI categorizes them. Patterns emerge. You see what you've been reaching toward.

## How It Works

- **TensorFlow.js + MobileNet** — Classification runs in your browser
- **IndexedDB** — Data stays on your device
- **No accounts** — No signup, no login
- **No upload** — Images never leave your machine

## Run It

### Backend (Ollama Vision)

```bash
# Make sure Ollama is running with a vision model
ollama pull llama3.2-vision

# Start the backend
cd backend
pip install -r requirements.txt
python main.py
```

Backend runs on http://localhost:8420

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on http://localhost:3000

### Quick Start (Both)

Terminal 1:
```bash
cd backend && python main.py
```

Terminal 2:
```bash
cd frontend && npm run dev
```

The frontend auto-detects the backend. If Ollama is available, it uses vision AI. Otherwise falls back to TensorFlow.js in the browser.

## Features

- **Gallery View** — Auto-categorized grid of images
- **Pin Board View** — Drag-and-drop arrangement
- **Folder Import** — Select entire folders
- **Category Editing** — Override AI categorizations
- **Export PNG** — Save your board

## Legacy Version

The original single-file prototype is still at `index.html`:

```bash
python -m http.server 8080
# Open http://localhost:8080
```

## Categories

| Category | Detected Content |
|----------|------------------|
| Personal | Pets, family, people |
| Travel | Beaches, mountains, landmarks |
| Career | Laptops, offices, professional |
| Wealth | Cars, homes, luxury items |
| Fitness | Gym, sports, health |
| Creative | Art, instruments, cameras |
| Home | Furniture, interiors, gardens |
| Food | Meals, drinks, restaurants |
| Relationships | Groups, couples, social |
| Inspiration | Default / uncategorized |

## Privacy

Your data never touches our servers. Period.

- Images processed locally via TensorFlow.js
- Board state stored in IndexedDB
- No analytics, no tracking, no cloud
- Export to PNG stays on your device

## Part Of

This is a [Willow](https://github.com/rudi193-cmd/Willow) app running on [Aionic OS](https://github.com/rudi193-cmd/SAFE).

---

ΔΣ=42

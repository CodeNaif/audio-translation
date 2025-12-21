# Audio Translation

Real-time audio translation app with a FastAPI backend and a Vite + React UI.

## Repository layout
- `backend/`: FastAPI service for transcription + translation
- `frontend/`: React UI

## Prerequisites
- Python 3.10+
- Node.js 18+
- `ffmpeg` installed (used by `pydub` to convert audio)
- OpenAI-compatible inference servers for:
  - Whisper (default: `http://0.0.0.0:8000`)
  - Gemma (default: `http://0.0.0.0:8001`)

## Backend setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional overrides
export WHISPER_BASE_URL="http://0.0.0.0:8000"
export WHISPER_MODEL="openai/whisper-large-v3"
export GEMMA_BASE_URL="http://0.0.0.0:8001"
export GEMMA_MODEL="google/gemma-3-4b-it"

uvicorn app.main:app --reload --port 9100
```

## Frontend setup
```bash
cd frontend
npm install
export VITE_API_URL="http://localhost:9100"
npm run dev
```

## How it works
1. The UI records or uploads audio and sends it to the backend.
2. The backend transcribes audio with Whisper and streams the translation from Gemma.

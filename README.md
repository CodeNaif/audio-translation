# Audio Translation

Real-time audio translation app with a FastAPI backend and a Vite + React UI.

## Repository layout
- `backend/`: FastAPI service for transcription + translation
- `frontend/`: React UI

## Prerequisites
- Python 3.10+
- Node.js 18+
- `ffmpeg` installed (used by `pydub` to convert audio)
- A realtime ASR server (WebSocket) for live streaming
- `OPENAI_API_KEY` only if using api.openai.com for realtime transcription
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
# OpenAI realtime ASR example:
export OPENAI_API_KEY="your-openai-key"
export OPENAI_REALTIME_URL="wss://api.openai.com/v1/realtime?intent=transcription"
export REALTIME_MODEL="gpt-4o-transcribe"

# Local realtime ASR example:
export OPENAI_REALTIME_URL="ws://localhost:8002/v1/realtime?intent=transcription"
export REALTIME_MODEL="openai/whisper-large-v3"
export REALTIME_LANGUAGE=""
export TRANSLATION_CHUNK_CHARS="40"
export TRANSLATION_CHUNK_INTERVAL="0.7"
export TRANSLATION_MIN_ALNUM="2"
export TRANSLATION_REDUNDANCY_OVERLAP="0.85"
export TRANSLATION_REDUNDANCY_MIN_TOKENS="3"
export WHISPER_BASE_URL="http://0.0.0.0:8000"
export WHISPER_MODEL="openai/whisper-large-v3"
export GEMMA_BASE_URL="http://0.0.0.0:8001"
export GEMMA_MODEL="google/gemma-3-4b-it"

uvicorn app.main:app --reload --port 9100
```

If `OPENAI_API_KEY` is not set, the backend defaults to `OPENAI_REALTIME_URL` on your local Docker host.
If your Docker realtime server requires a custom header, set `REALTIME_HEADERS_JSON` (for example: `{"Authorization":"Bearer local-token"}` or `{"api-key":"local-token"}`).

## Local realtime ASR (offline, Whisper docker)
This repo includes a small WebSocket ASR shim that accepts PCM16 16kHz audio and calls your local Whisper HTTP API (`/v1/audio/transcriptions`) in a rolling window. It emits transcript deltas so the rest of the pipeline can stay realtime.

```bash
cd local-asr
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Point to your Whisper docker
export WHISPER_BASE_URL="http://localhost:8000"
export WHISPER_MODEL="openai/whisper-large-v3"

# Start websocket ASR server
python server.py
```

Then set the backend to use it:
```bash
export OPENAI_REALTIME_URL="ws://localhost:8002/v1/realtime?intent=transcription"
```

Note: this shim re-runs Whisper on a rolling window. It provides near-realtime deltas, but is less efficient than a native streaming ASR server and may repeat or correct earlier text.

## Frontend setup
```bash
cd frontend
npm install
export VITE_API_URL="http://localhost:9100"
npm run dev
```

## How it works
1. The UI streams live PCM audio over WebSocket while recording.
2. The backend proxies audio to the OpenAI realtime transcription API, then streams translation chunks from Gemma back to the UI.
3. Uploads still use the `/transcribe` + `/translate` REST flow for one-shot processing.

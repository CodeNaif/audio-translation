# Audio Translation

Real-time audio translation app with a FastAPI backend and a Vite + React UI. It auto-detects the spoken language during transcription, then translates the text to English or Arabic. You can extend the UI to support 150+ languages that Gemma can handle by adding new language options.

## Repository layout
- `backend/`: FastAPI service for transcription + translation
- `frontend/`: React UI

## Demo assets
Recording example:



https://github.com/user-attachments/assets/cd7b2071-c36b-445f-9e93-0c562978b8c6



Upload example (Hindi audio):


https://github.com/user-attachments/assets/288ed34e-a14b-4fa1-bfcd-8f4e756a1377


Sample Hindi audio file you can try:
[what_do_you_do_in_hindi.wav](https://github.com/user-attachments/files/24396056/what_do_you_do_in_hindi.wav)


## Prerequisites
- Python 3.11.9 recommended (3.10+ supported). Python 3.13 may fail due to `pydub`/`audioop`.
- Node.js 18+
- `ffmpeg` installed (used by `pydub` to convert audio)

## Hardware Requirements

- Recommended: **2× GPUs (24GB VRAM each or higher)**
- Designed for large models and multi-GPU workloads

If your hardware does not meet these requirements, you can still try the project using
**smaller / lightweight models**, but change the models in the .env, although performance and accuracy may be reduced.

## Configuration (.env)
Use a single env file at the repo root for both Docker Compose and the backend.
```bash
cp .env.example .env
# Edit .env with your HUGGING_FACE_HUB_TOKEN, models, ports, and base URLs
```

## Inference servers (Docker Compose)
The dev compose file builds a `vllm-audio` image and runs Whisper + Gemma.
```bash
docker compose --env-file .env -f backend/dev_env/docker-compose.yaml build whisper
docker compose --env-file .env -f backend/dev_env/docker-compose.yaml up -d
```
Notes:
- Requires Linux host networking (`network_mode: host`).
- Use `WHISPER_CUDA_VISIBLE_DEVICES` in `.env` to select a GPU.

Stop the services:
```bash
docker compose --env-file .env -f backend/dev_env/docker-compose.yaml stop
```

First time only: you must run the `build whisper` command before `up`.

## Backend setup (uv) (recommended)
Uses `backend/pyproject.toml` and `backend/uv.lock`.
```bash
cd backend
uv sync --python 3.11.9
# Ensure .env exists at the repo root
uv run uvicorn app.main:app --reload --port 9100
```

## Backend setup (venv)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Required configuration
# Ensure .env exists at the repo root
uvicorn app.main:app --reload --port 9100
```

## Backend setup (conda)
```bash
conda create -n audio-translation python=3.11.9
conda activate audio-translation
cd backend
pip install -r requirements.txt
# Ensure .env exists at the repo root
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

If you run into any problems, feel free to reach out or open an issue in the repo.

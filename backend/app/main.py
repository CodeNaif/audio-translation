from io import BytesIO

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydub import AudioSegment
from app.clients import GemmaClient, WhisperClient

app = FastAPI(title="Translation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

whisper_client = WhisperClient()
gemma_client = GemmaClient()

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    data = await audio.read()
    file_obj = BytesIO(data)

    content_type = (audio.content_type or "").split(";")[0]
    if content_type in {"audio/webm", "audio/ogg", "audio/opus"} or (
        audio.filename and audio.filename.endswith((".webm", ".ogg", ".opus"))
    ):
        try:
            buf = BytesIO()
            AudioSegment.from_file(BytesIO(data)).export(buf, format="wav")  # let ffmpeg detect
            buf.seek(0)
            file_obj = buf
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not convert audio: {exc}")

    try:
        text = whisper_client.transcribe(file_obj)
        return {"text": text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")

@app.post("/translate")
async def translate(
    text: str = Form(..., description="Text to translate"),
    target_language: str = Form(..., description="e.g., Arabic, French"),
):
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    try:
        def generate():
            for chunk in gemma_client.translate_stream(text=text, target_language=target_language):
                yield chunk

        return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Translation failed: {exc}")

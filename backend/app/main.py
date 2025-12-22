import asyncio
import json
import os
import time
from collections import deque
from io import BytesIO
from queue import Queue
from threading import Thread
from typing import Any

import websockets
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
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


def _extract_transcript(event: dict[str, Any]) -> tuple[str | None, bool]:
    event_type = str(event.get("type", ""))
    if "transcript" not in event_type and "transcription" not in event_type:
        return None, False

    delta = event.get("delta")
    if isinstance(delta, str):
        return delta, False
    if isinstance(delta, dict):
        delta_text = delta.get("text") or delta.get("transcript")
        if isinstance(delta_text, str):
            return delta_text, False

    for key in ("text", "transcript"):
        value = event.get(key)
        if isinstance(value, str):
            is_final = event_type.endswith((".done", ".completed", ".final"))
            return value, is_final

    item = event.get("item")
    if isinstance(item, dict):
        content = item.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    value = block.get("text") or block.get("transcript")
                    if isinstance(value, str):
                        return value, True
    return None, False


def _normalize_chunk(text: str) -> str:
    return " ".join(text.lower().split())


def _is_meaningful_text(text: str, min_chars: int) -> bool:
    count = 0
    for char in text:
        if char.isalnum():
            count += 1
            if count >= min_chars:
                return True
    return False


def _run_translation(text: str, target_language: str, output: Queue[str | None]) -> None:
    instruction = (
        f"Translate the following transcript chunk to {target_language}. "
        "Return only the translation of this chunk with no extra commentary. "
        "If the chunk is incomplete, still translate it as-is. "
        f"Chunk: {text}"
    )
    try:
        for chunk in gemma_client.translate_stream(
            text=text,
            target_language=target_language,
            instruction=instruction,
        ):
            output.put(chunk)
    finally:
        output.put(None)


async def _stream_translation(text: str, target_language: str, send_event) -> None:
    if not text.strip():
        return
    output: Queue[str | None] = Queue()
    thread = Thread(
        target=_run_translation,
        args=(text, target_language, output),
        daemon=True,
    )
    thread.start()
    while True:
        item = await asyncio.to_thread(output.get)
        if item is None:
            break
        await send_event({"type": "translation_delta", "text": item})


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


@app.websocket("/ws/stream")
async def stream_translate(websocket: WebSocket):
    await websocket.accept()
    try:
        start_payload = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1003)
        return

    if start_payload.get("type") != "start":
        await websocket.close(code=1003)
        return

    target_language = start_payload.get("target_language", "Arabic")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    realtime_url = os.environ.get("OPENAI_REALTIME_URL")
    if not realtime_url:
        if api_key:
            realtime_url = "wss://api.openai.com/v1/realtime?intent=transcription"
        else:
            realtime_url = "ws://localhost:8000/v1/realtime?intent=transcription"
    if not api_key and "api.openai.com" in realtime_url:
        await websocket.send_json({"type": "error", "message": "OPENAI_API_KEY is required for api.openai.com."})
        await websocket.close(code=1011)
        return
    default_model = os.environ.get("REALTIME_MODEL")
    if not default_model:
        default_model = "gpt-4o-transcribe" if "api.openai.com" in realtime_url else "openai/whisper-large-v3"

    session_payload = {
        "type": "transcription_session.update",
        "input_audio_format": "pcm16",
        "input_audio_transcription": {
            "model": default_model,
            "prompt": os.environ.get("REALTIME_PROMPT", ""),
            "language": os.environ.get("REALTIME_LANGUAGE", ""),
        },
        "turn_detection": {
            "type": "server_vad",
            "threshold": float(os.environ.get("REALTIME_VAD_THRESHOLD", "0.5")),
            "prefix_padding_ms": int(os.environ.get("REALTIME_PREFIX_PADDING_MS", "300")),
            "silence_duration_ms": int(os.environ.get("REALTIME_SILENCE_MS", "500")),
        },
        "input_audio_noise_reduction": {
            "type": os.environ.get("REALTIME_NOISE_REDUCTION", "near_field"),
        },
    }

    send_lock = asyncio.Lock()

    async def send_event(payload: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    translate_queue: asyncio.Queue[str | None] = asyncio.Queue()
    pending_text = ""
    last_flush = time.monotonic()
    chunk_chars = int(os.environ.get("TRANSLATION_CHUNK_CHARS", "40"))
    chunk_interval = float(os.environ.get("TRANSLATION_CHUNK_INTERVAL", "0.7"))
    min_alnum = int(os.environ.get("TRANSLATION_MIN_ALNUM", "2"))
    recent_chunks = deque(maxlen=6)

    async def translation_worker() -> None:
        while True:
            text = await translate_queue.get()
            if text is None:
                translate_queue.task_done()
                break
            await _stream_translation(text=text, target_language=target_language, send_event=send_event)
            translate_queue.task_done()

    try:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        extra_headers = os.environ.get("REALTIME_HEADERS_JSON", "")
        if extra_headers:
            try:
                headers.update(json.loads(extra_headers))
            except json.JSONDecodeError:
                await send_event({"type": "error", "message": "REALTIME_HEADERS_JSON must be valid JSON."})
                await websocket.close(code=1011)
                return
        if not headers:
            headers = None
        async with websockets.connect(
            realtime_url,
            additional_headers=headers,
            max_size=2**20,
        ) as openai_ws:
            await openai_ws.send(json.dumps(session_payload))
            await send_event({"type": "status", "message": "Realtime transcription connected."})

            async def read_client() -> None:
                while True:
                    message = await websocket.receive_json()
                    msg_type = message.get("type")
                    if msg_type == "audio":
                        data = message.get("data")
                        if data:
                            await openai_ws.send(
                                json.dumps({"type": "input_audio_buffer.append", "audio": data})
                            )
                    elif msg_type == "stop":
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        break

            async def read_openai() -> None:
                nonlocal pending_text, last_flush
                async for raw in openai_ws:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    delta, is_final = _extract_transcript(event)
                    if not delta or not delta.strip():
                        continue

                    pending_text += delta
                    await send_event({"type": "transcript_delta", "text": delta})

                    now = time.monotonic()
                    if is_final or len(pending_text) >= chunk_chars or now - last_flush >= chunk_interval:
                        chunk = pending_text.strip()
                        pending_text = ""
                        last_flush = now
                        if chunk and _is_meaningful_text(chunk, min_alnum):
                            normalized = _normalize_chunk(chunk)
                            if normalized and normalized not in recent_chunks:
                                recent_chunks.append(normalized)
                                await translate_queue.put(chunk)

            translate_task = asyncio.create_task(translation_worker())
            client_task = asyncio.create_task(read_client())
            openai_task = asyncio.create_task(read_openai())

            done, pending = await asyncio.wait(
                {client_task, openai_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

            final_chunk = pending_text.strip()
            if final_chunk and _is_meaningful_text(final_chunk, min_alnum):
                normalized = _normalize_chunk(final_chunk)
                if normalized and normalized not in recent_chunks:
                    recent_chunks.append(normalized)
                    await translate_queue.put(final_chunk)

            await translate_queue.put(None)
            await translate_queue.join()
            await translate_task
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await send_event({"type": "error", "message": f"Realtime streaming failed: {exc}"})
        await websocket.close(code=1011)


@app.websocket("/ws/translate")
async def translate_text_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        start_payload = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1003)
        return

    if start_payload.get("type") != "start":
        await websocket.close(code=1003)
        return

    target_language = start_payload.get("target_language", "Arabic")

    async def send_event(payload: dict[str, Any]) -> None:
        await websocket.send_json(payload)

    await send_event({"type": "status", "message": "Translation stream ready."})

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            if msg_type == "text":
                text = (message.get("text") or "").strip()
                if text:
                    await _stream_translation(text=text, target_language=target_language, send_event=send_event)
            elif msg_type == "stop":
                break
    except WebSocketDisconnect:
        return

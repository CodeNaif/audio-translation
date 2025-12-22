import asyncio
import base64
import contextlib
import io
import json
import logging
import os
import time
import wave

from openai import OpenAI
import websockets

HOST = os.environ.get("LOCAL_ASR_HOST", "0.0.0.0")
PORT = int(os.environ.get("LOCAL_ASR_PORT", "8002"))

WHISPER_BASE_URL = os.environ.get("WHISPER_BASE_URL", "http://localhost:8000")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "openai/whisper-large-v3")
WHISPER_API_KEY = os.environ.get("WHISPER_API_KEY", "EMPTY")

SAMPLE_RATE = int(os.environ.get("ASR_SAMPLE_RATE", "16000"))
WINDOW_SEC = float(os.environ.get("ASR_WINDOW_SEC", "12"))
TRANSCRIBE_INTERVAL = float(os.environ.get("ASR_TRANSCRIBE_INTERVAL", "0.7"))
MIN_AUDIO_SEC = float(os.environ.get("ASR_MIN_AUDIO_SEC", "0.8"))

logging.basicConfig(
    level=os.environ.get("ASR_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("local_asr")

client = OpenAI(api_key=WHISPER_API_KEY, base_url=f"{WHISPER_BASE_URL}/v1", timeout=60)


def _delta_text(previous: str, current: str) -> str:
    match_len = 0
    for old_char, new_char in zip(previous, current):
        if old_char != new_char:
            break
        match_len += 1
    return current[match_len:]


def _pcm_to_wav_bytes(pcm: bytes, sample_rate: int) -> io.BytesIO:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    buf.seek(0)
    return buf


def _transcribe_pcm(pcm: bytes, sample_rate: int) -> str:
    if not pcm:
        return ""
    wav_buf = _pcm_to_wav_bytes(pcm, sample_rate)
    resp = client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=("audio.wav", wav_buf, "audio/wav"),
    )
    return resp.text or ""


async def _transcribe_loop(websocket, state):
    last_run = 0.0
    min_bytes = int(SAMPLE_RATE * MIN_AUDIO_SEC * 2)
    max_bytes = int(SAMPLE_RATE * WINDOW_SEC * 2)

    while True:
        await asyncio.sleep(TRANSCRIBE_INTERVAL)
        if state["closed"]:
            break
        if len(state["buffer"]) < min_bytes:
            continue
        if time.monotonic() - last_run < TRANSCRIBE_INTERVAL:
            continue

        audio_bytes = bytes(state["buffer"][-max_bytes:])
        last_run = time.monotonic()

        try:
            text = await asyncio.to_thread(_transcribe_pcm, audio_bytes, SAMPLE_RATE)
        except Exception as exc:
            logger.warning("transcribe failed: %s", exc)
            continue

        if not text:
            logger.debug("empty transcription result")
            continue

        delta = _delta_text(state["last_text"], text)
        if delta:
            logger.info("transcript delta (%s chars)", len(delta))
            await websocket.send(json.dumps({"type": "transcript.delta", "delta": delta}))
            state["last_text"] = text


async def handler(websocket):
    path = getattr(websocket, "path", None)
    if path is None:
        request = getattr(websocket, "request", None)
        path = getattr(request, "path", "")
    if path and not path.startswith("/v1/realtime"):
        logger.warning("rejecting path %s", path)
        await websocket.close(code=1008)
        return

    logger.info("client connected path=%s", path or "<unknown>")

    state = {"buffer": bytearray(), "closed": False, "last_text": ""}
    worker = asyncio.create_task(_transcribe_loop(websocket, state))

    try:
        async for message in websocket:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = payload.get("type")
            if msg_type == "input_audio_buffer.append":
                audio_b64 = payload.get("audio")
                if not audio_b64:
                    continue
                try:
                    state["buffer"].extend(base64.b64decode(audio_b64))
                    if len(state["buffer"]) % (SAMPLE_RATE * 2) < 4096:
                        logger.debug("buffer size=%s bytes", len(state["buffer"]))
                except Exception:
                    continue
            elif msg_type in {"input_audio_buffer.commit", "stop"}:
                break
            else:
                logger.debug("ignored message type=%s", msg_type)
    finally:
        state["closed"] = True
        if state["buffer"]:
            try:
                text = await asyncio.to_thread(_transcribe_pcm, bytes(state["buffer"]), SAMPLE_RATE)
                if text:
                    delta = _delta_text(state["last_text"], text)
                    if delta:
                        await websocket.send(json.dumps({"type": "transcript.final", "text": delta}))
            except Exception as exc:
                logger.warning("final transcribe failed: %s", exc)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
        logger.info("client disconnected")


async def main():
    logger.info(
        "starting local ASR WS server on ws://%s:%s (whisper=%s)",
        HOST,
        PORT,
        WHISPER_BASE_URL,
    )
    async with websockets.serve(handler, HOST, PORT, max_size=2**20):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


class WhisperClient:
    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
    ) -> None:
        base_url = base_url or _require_env("WHISPER_BASE_URL")
        model_name = model_name or _require_env("WHISPER_MODEL")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        self.client = OpenAI(api_key="EMPTY", base_url=f"{base_url}/v1", timeout=3600)
        self.model_name = model_name

    def transcribe(self, file_input) -> str:
        if isinstance(file_input, (str, os.PathLike)):
            with open(file_input, "rb") as f:
                resp = self.client.audio.transcriptions.create(
                    model=self.model_name,
                    file=f,
                )
            return resp.text

        file_input.seek(0)
        resp = self.client.audio.transcriptions.create(
            model=self.model_name, file=file_input
        )
        return resp.text


class GemmaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
    ) -> None:
        base_url = base_url or _require_env("GEMMA_BASE_URL")
        model_name = model_name or _require_env("GEMMA_MODEL")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        self.client = OpenAI(api_key="EMPTY", base_url=f"{base_url}/v1", timeout=3600)
        self.model_name = model_name

    def translate(self, text: str, target_language: str) -> str:
        messages = [
            {"role": "system", "content": [{"type": "text", "text": "You are a helpful translation assistant."}]},
            {"role": "user", "content": [{"type": "text", "text": f"Translate the following text to {target_language} just return the translation without reasoning. Text: {text}"}]},
        ]
        resp = self.client.chat.completions.create(model=self.model_name, messages=messages)
        return resp.choices[0].message.content

    def translate_stream(self, text: str, target_language: str):
        messages = [
            {"role": "system", "content": [{"type": "text", "text": "You are a helpful translation assistant."}]},
            {"role": "user", "content": [{"type": "text", "text": f"Translate the following text to {target_language} just return the translation without reasoning. Text: {text}"}]},
        ]
        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content


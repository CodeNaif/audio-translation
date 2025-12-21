import os
from openai import OpenAI


class WhisperClient:
    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
    ) -> None:
        base_url = base_url or os.environ.get("WHISPER_BASE_URL", "http://0.0.0.0:8000")
        model_name = model_name or os.environ.get("WHISPER_MODEL", "openai/whisper-large-v3")
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
        base_url = base_url or os.environ.get("GEMMA_BASE_URL", "http://0.0.0.0:8001")
        model_name = model_name or os.environ.get("GEMMA_MODEL", "google/gemma-3-4b-it")
        self.client = OpenAI(api_key="EMPTY", base_url=f"{base_url}/v1", timeout=3600)
        self.model_name = model_name

    def translate(self, text: str, target_language: str) -> str:
        messages = [
            {"role": "system", "content": [{"type": "text", "text": "You are a helpful translation assistant."}]},
            {"role": "user", "content": [{"type": "text", "text": f"Translate the following text to {target_language} just return the translation. Text: {text}"}]},
        ]
        resp = self.client.chat.completions.create(model=self.model_name, messages=messages)
        return resp.choices[0].message.content

    def translate_stream(self, text: str, target_language: str):
        messages = [
            {"role": "system", "content": [{"type": "text", "text": "You are a helpful translation assistant."}]},
            {"role": "user", "content": [{"type": "text", "text": f"Translate the following text to {target_language} just return the translation. Text: {text}"}]},
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





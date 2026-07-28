from __future__ import annotations

import asyncio
import base64

from core.dependencies import OrangeDeps


class AudioService:
    """Validates and transcribes bounded audio payloads."""

    max_audio_bytes = 10 * 1024 * 1024
    allowed_media_types = {
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
    }

    def __init__(self, deps: OrangeDeps):
        self._deps = deps

    async def transcribe(
        self,
        base64_audio: str,
        media_type: str = "audio/webm",
    ) -> str:
        if not self._deps.settings.gemini_api_key:
            return "[NOT_CONFIGURED] GOOGLE_API_KEY is required for audio transcription."
        if not isinstance(base64_audio, str):
            return "[VALIDATION_ERROR] Audio payload must be base64 text."
        if len(base64_audio) > ((self.max_audio_bytes + 2) // 3) * 4 + 16:
            return "[VALIDATION_ERROR] Audio exceeds 10 MB."
        normalized_media_type = str(media_type or "").split(";", 1)[0].strip().lower()
        if normalized_media_type not in self.allowed_media_types:
            return "[VALIDATION_ERROR] Unsupported audio format."
        try:
            audio_bytes = base64.b64decode(base64_audio, validate=True)
        except (ValueError, TypeError):
            return "[VALIDATION_ERROR] Audio payload is not valid base64."
        if not audio_bytes:
            return "[VALIDATION_ERROR] Audio payload is empty."
        if len(audio_bytes) > self.max_audio_bytes:
            return "[VALIDATION_ERROR] Audio exceeds 10 MB."

        from pydantic_ai import Agent
        from pydantic_ai.messages import BinaryContent
        from core.agent import LITE_MODEL

        try:
            transcriber = Agent(LITE_MODEL, defer_model_check=True)
            result = await asyncio.wait_for(
                transcriber.run(
                    [
                        (
                            "Transcribe this recording. Return only the spoken text in its "
                            "original language, without commentary or Markdown. Return an "
                            "empty string when no speech is audible."
                        ),
                        BinaryContent(
                            data=audio_bytes,
                            media_type=normalized_media_type,
                        ),
                    ],
                    model_settings={"timeout": 90.0},
                ),
                timeout=100.0,
            )
            return str(result.output or "").strip()
        except Exception as exc:
            return f"[PROVIDER_ERROR] Audio transcription failed: {type(exc).__name__}"

"""ElevenLabs Flash v2.5 TTS provider — full implementation."""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from glc.voice.tts.base import SynthesizeResult, TTSError, TTSProvider
from glc.voice.tts.providers.elevenlabs.schemas import ElevenLabsRequest

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
FREE_TIER_LIMIT = 10_000
QUOTA_FILE = Path.home() / ".glc" / "elevenlabs_quota.json"


def _chunk_text(text: str, max_chars: int = 5000) -> list[str]:
    if not text:
        return [""]
    if len(text) <= max_chars:
        return [text]
    sentences: list[str] = re.split(r"(?<=[.?!])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(sentence)
        elif len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.rstrip())
            current = sentence
        else:
            current = (current + " " + sentence).lstrip() if current else sentence
    if current:
        chunks.append(current.rstrip())
    return chunks if chunks else [text]


class Provider(TTSProvider):
    name = "elevenlabs"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._api_key: str = os.environ.get("ELEVENLABS_API_KEY", "")
        self._voice_id: str = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)

    async def synthesize(self, text: str, voice_id: str | None = None) -> SynthesizeResult:
        if not text:
            return SynthesizeResult(
                audio_b64="",
                mime="audio/mpeg",
                sample_rate=44100,
                provider="elevenlabs",
            )
        effective_voice = voice_id or self._voice_id
        if mock := self.config.get("mock"):
            self._check_quota(text, mock=mock)
            return await mock.synthesize(text, effective_voice)
        self._check_quota(text)
        chunks = _chunk_text(text)
        raw_bytes = b""
        for chunk in chunks:
            raw_bytes += await self._call_upstream(chunk, effective_voice)
        self._persist_quota(len(text))
        return SynthesizeResult(
            audio_b64=base64.b64encode(raw_bytes).decode("ascii"),
            mime="audio/mpeg",
            sample_rate=44100,
            provider="elevenlabs",
            cost_usd=0.0,
        )

    def _check_quota(self, text: str, mock: Any | None = None) -> None:
        if mock is not None:
            used: int = mock.monthly_chars_used
            limit: int = mock.monthly_chars_limit
        else:
            used, limit = self._load_quota()
        if used + len(text) > limit:
            raise TTSError(
                f"monthly quota limit exceeded: {used + len(text)} > {limit}",
                status=429,
            )

    def _load_quota(self) -> tuple[int, int]:
        month_key = datetime.now().strftime("%Y-%m")
        if QUOTA_FILE.exists():
            try:
                data: dict[str, Any] = json.loads(QUOTA_FILE.read_text())
                used = int(data.get(month_key, 0))
            except (json.JSONDecodeError, ValueError):
                used = 0
        else:
            used = 0
        return used, FREE_TIER_LIMIT

    def _persist_quota(self, chars_added: int) -> None:
        month_key = datetime.now().strftime("%Y-%m")
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if QUOTA_FILE.exists():
            try:
                data = json.loads(QUOTA_FILE.read_text())
            except (json.JSONDecodeError, ValueError):
                data = {}
        data[month_key] = int(data.get(month_key, 0)) + chars_added
        QUOTA_FILE.write_text(json.dumps(data))

    async def _call_upstream(self, text: str, voice_id: str) -> bytes:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        payload = ElevenLabsRequest(text=text).model_dump(exclude_none=True)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={"xi-api-key": self._api_key},
                    json=payload,
                )
                response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as exc:
            raise TTSError(str(exc), status=exc.response.status_code) from exc
        except httpx.RequestError as exc:
            raise TTSError(str(exc), status=503) from exc

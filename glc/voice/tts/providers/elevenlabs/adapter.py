"""ElevenLabs Flash v2.5 TTS provider.

Architectural decisions (set by Hari — do not change without team discussion):
  - Mock delegation:  first check in synthesize(); quota still runs before delegation.
  - Quota method:     _check_quota(text, mock=None) — implemented by Vichitravir.
  - HTTP wrapper:     _call_upstream(text, voice_id) -> bytes — implemented by Anshul.
  - Chunking:         _chunk_text(text, max_chars=5000) -> list[str] — implemented by Anshul.
  - Audio merge:      raw bytes from all chunks concatenated before a single b64 encode.
  - text_len record:  always total len(text), not per-chunk.
  - Quota state:      mock path reads mock.monthly_chars_used / mock.monthly_chars_limit;
                      real path persists to ~/.glc/elevenlabs_quota.json keyed by YYYY-MM.
"""

from __future__ import annotations

import base64
import os

import httpx

from glc.voice.tts.base import SynthesizeResult, TTSError, TTSProvider
from glc.voice.tts.providers.elevenlabs.schemas import ElevenLabsRequest

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class Provider(TTSProvider):
    name = "elevenlabs"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._api_key: str = os.environ.get("ELEVENLABS_API_KEY", "")
        self._voice_id: str = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)

    async def synthesize(self, text: str, voice_id: str | None = None) -> SynthesizeResult:
        mock = self.config.get("mock")
        if mock is not None:
            # Quota check must run before delegating to the mock.
            self._check_quota(text, mock=mock)
            return await mock.synthesize(text, voice_id)

        # Real path: short-circuit for empty text to avoid a pointless API round-trip.
        if not text:
            return SynthesizeResult(
                audio_b64="",
                mime="audio/mpeg",
                sample_rate=44100,
                provider="elevenlabs",
                cost_usd=0.0,
            )

        self._check_quota(text)
        chunks = self._chunk_text(text)
        audio_bytes = b""
        for chunk in chunks:
            audio_bytes += await self._call_upstream(chunk, voice_id or self._voice_id)
        return SynthesizeResult(
            audio_b64=base64.b64encode(audio_bytes).decode("ascii"),
            mime="audio/mpeg",
            sample_rate=44100,
            provider="elevenlabs",
            cost_usd=0.0,
        )

    def _check_quota(self, text: str, mock: object | None = None) -> None:
        """Pre-flight monthly character quota check.

        TODO (Vichitravir): implement.
        Mock path : read mock.monthly_chars_used and mock.monthly_chars_limit.
        Real path : read/write ~/.glc/elevenlabs_quota.json keyed by YYYY-MM.
        Raise TTSError("monthly quota limit exceeded", status=429) when
        monthly_chars_used + len(text) > monthly_chars_limit.
        The error message MUST contain "quota" or "limit" (tests assert this).
        """

    async def _call_upstream(self, text: str, voice_id: str) -> bytes:
        """POST one chunk to the ElevenLabs API and return raw MP3 bytes.

        Endpoint : POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
        Auth     : xi-api-key header (NOT Authorization: Bearer)
        Body     : ElevenLabsRequest(text=text).model_dump(exclude_none=True)
        Return   : response.content  (raw MP3 bytes)

        Raises httpx.HTTPStatusError on non-2xx and httpx.RequestError on
        network failure. Translating those into TTSError is Vichitravir's
        error-handling deliverable (wraps this call).
        """
        url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
        headers = {"xi-api-key": self._api_key}
        body = ElevenLabsRequest(text=text).model_dump(exclude_none=True)
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
        return response.content

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 5000) -> list[str]:
        """Split text into chunks of at most max_chars on sentence boundaries.

        TODO (Anshul): implement.
        Rules:
          - Split on . ? ! without cutting mid-word.
          - A single token longer than max_chars is kept as one unsplit chunk.
          - Empty string returns [].
        Current stub: returns the whole string as a single chunk.
        """
        if not text:
            return []
        return [text]

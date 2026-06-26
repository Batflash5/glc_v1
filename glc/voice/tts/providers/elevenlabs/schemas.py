"""Channel-specific Pydantic types for the ElevenLabs TTS provider."""

from __future__ import annotations

from pydantic import BaseModel


class ElevenLabsVoiceSettings(BaseModel):
    """Voice generation settings for ElevenLabs Flash v2.5."""

    stability: float = 0.5
    similarity_boost: float = 0.75


class ElevenLabsRequest(BaseModel):
    """Request body for POST /v1/text-to-speech/{voice_id}."""

    text: str
    model_id: str = "eleven_flash_v2_5"
    voice_settings: ElevenLabsVoiceSettings | None = None

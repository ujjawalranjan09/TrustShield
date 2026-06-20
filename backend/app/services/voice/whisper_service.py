"""Voice transcription service — Whisper (local) or Deepgram (cloud).

Config-driven via settings.voice_provider. Falls back to mock if
neither is available.
"""

import io
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class WhisperService:
    """Transcribe audio to text using the configured provider."""

    def __init__(self):
        self._provider = settings.voice_provider
        self._whisper_model = None
        self._deepgram_client = None

        if self._provider == "whisper":
            self._init_whisper()
        elif self._provider == "deepgram":
            self._init_deepgram()

    def _init_whisper(self):
        try:
            from faster_whisper import WhisperModel
            self._whisper_model = WhisperModel(
                settings.whisper_model_size,
                device="cpu",
                compute_type="int8",
            )
            logger.info("Whisper model loaded: %s", settings.whisper_model_size)
        except ImportError:
            logger.warning("faster-whisper not installed, falling back to mock")
            self._provider = "mock"
        except Exception as exc:
            logger.warning("Failed to load Whisper model: %s", exc)
            self._provider = "mock"

    def _init_deepgram(self):
        if not settings.deepgram_api_key:
            logger.warning("Deepgram API key not set, falling back to mock")
            self._provider = "mock"
            return
        try:
            from deepgram import DeepgramClient
            self._deepgram_client = DeepgramClient(settings.deepgram_api_key)
            logger.info("Deepgram client initialized")
        except ImportError:
            logger.warning("deepgram-sdk not installed, falling back to mock")
            self._provider = "mock"
        except Exception as exc:
            logger.warning("Failed to init Deepgram: %s", exc)
            self._provider = "mock"

    async def transcribe(self, audio_data: bytes, language: str = "hi") -> Optional[str]:
        """Transcribe audio bytes to text.

        Args:
            audio_data: Raw audio (PCM 16-bit 16kHz or WebM/Opus).
            language: Language hint.

        Returns:
            Transcribed text or None if transcription fails.
        """
        if self._provider == "whisper":
            return self._transcribe_whisper(audio_data, language)
        elif self._provider == "deepgram":
            return await self._transcribe_deepgram(audio_data, language)
        else:
            return self._transcribe_mock(audio_data)

    def _transcribe_whisper(self, audio_data: bytes, language: str) -> Optional[str]:
        try:
            import numpy as np
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            segments, info = self._whisper_model.transcribe(
                audio_np, language=language, beam_size=5
            )
            return " ".join(seg.text for seg in segments)
        except Exception as exc:
            logger.error("Whisper transcription failed: %s", exc)
            return None

    async def _transcribe_deepgram(self, audio_data: bytes, language: str) -> Optional[str]:
        try:
            from deepgram import PrerecordedOptions
            buffer_data = io.BytesIO(audio_data)
            buffer_data.name = "audio.webm"
            options = PrerecordedOptions(
                model="nova-3",
                language=language,
                smart_format=True,
            )
            response = await self._deepgram_client.listen.prerecorded.transcribe_file(
                buffer_data, options
            )
            return response.results.channels[0].alternatives[0].transcript
        except Exception as exc:
            logger.error("Deepgram transcription failed: %s", exc)
            return None

    def _transcribe_mock(self, audio_data: bytes) -> Optional[str]:
        """Mock transcription for development/testing."""
        return "Mock transcription: please share your OTP for verification"


# Singleton
_service: Optional[WhisperService] = None


def get_whisper_service() -> WhisperService:
    global _service
    if _service is None:
        _service = WhisperService()
    return _service

"""Speech utilities - Text-to-Speech and Speech-to-Text using OpenAI."""
import asyncio
import base64
import io
from openai import AsyncOpenAI
from ..config import get_settings, logger

_openai_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Get OpenAI async client."""
    global _openai_client
    if _openai_client is None:
        settings = get_settings()
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def transcribe_audio(audio_bytes: bytes, format: str = "wav") -> str:
    """
    Convert speech to text using OpenAI Whisper.

    Args:
        audio_bytes: Raw audio data
        format: Audio format (wav, mp3, webm, etc.)

    Returns:
        Transcribed text
    """
    client = get_openai_client()

    try:
        # Create a file-like object for the API
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"audio.{format}"

        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )
        return response.strip()
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return ""


async def generate_speech(text: str, voice: str = "alloy") -> bytes:
    """
    Convert text to speech using OpenAI TTS.

    Args:
        text: Text to convert to speech
        voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)

    Returns:
        Audio bytes in mp3 format
    """
    client = get_openai_client()

    try:
        response = await client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            response_format="mp3",
        )
        return response.content
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        raise


async def generate_speech_streaming(text: str, voice: str = "alloy"):
    """
    Stream TTS audio chunk by chunk.

    Args:
        text: Text to convert to speech
        voice: Voice to use

    Yields:
        Audio chunks
    """
    client = get_openai_client()

    try:
        response = await client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            response_format="pcm",  # Raw PCM for streaming
        )

        # Yield in chunks
        chunk_size = 4096
        content = response.content
        for i in range(0, len(content), chunk_size):
            yield content[i:i + chunk_size]
    except Exception as e:
        logger.error(f"Streaming TTS failed: {e}")
        raise


def audio_to_base64(audio_bytes: bytes) -> str:
    """Convert audio bytes to base64 string."""
    return base64.b64encode(audio_bytes).decode("utf-8")


def base64_to_audio(base64_str: str) -> bytes:
    """Convert base64 string to audio bytes."""
    return base64.b64decode(base64_str)

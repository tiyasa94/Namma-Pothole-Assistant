"""
Voice transcription service — supports Hindi, English, and Kannada.

Architecture:
  - Accepts audio as base64-encoded WAV/MP3/OGG (max ~10MB)
  - Uses SpeechRecognition library with Google Speech Recognition
    (free, no API key needed — uses the public endpoint)
  - Language auto-detection via langdetect
  - Non-English text translated to English via deep_translator (Google Translate, free)
  - Returns structured VoiceTranscript with original text, detected language,
    and English translation

Supported languages:
  - en  English
  - hi  Hindi (हिंदी)
  - kn  Kannada (ಕನ್ನಡ)
"""
from __future__ import annotations

import base64
import io
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Language config ────────────────────────────────────────────────────────────

# BCP-47 language codes for Google Speech Recognition
LANG_TO_BCP47 = {
    "en": "en-IN",   # English (India accent)
    "hi": "hi-IN",   # Hindi
    "kn": "kn-IN",   # Kannada
}

# Human-readable names
LANG_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
}

SUPPORTED_LANGS = list(LANG_TO_BCP47.keys())


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class VoiceTranscript:
    original_text: str
    detected_language: str          # "en" | "hi" | "kn"
    language_name: str              # "English" | "Hindi" | "Kannada"
    english_text: str               # always English, for ML/DB storage
    confidence: float               # 0.0–1.0 (estimated)
    error: Optional[str] = None


# ── Audio decoding ─────────────────────────────────────────────────────────────

def _decode_audio(audio_base64: str) -> bytes:
    """Decode base64-encoded audio bytes."""
    if "," in audio_base64:
        audio_base64 = audio_base64.split(",", 1)[1]
    audio_base64 += "=" * (-len(audio_base64) % 4)
    return base64.b64decode(audio_base64)


# ── Language detection ─────────────────────────────────────────────────────────

def _detect_language(text: str) -> str:
    """
    Detect language from transcribed text.
    Returns "en", "hi", or "kn" — defaults to "en" if detection fails.
    """
    if not text.strip():
        return "en"
    try:
        from langdetect import detect
        lang = detect(text)
        # langdetect returns ISO 639-1 codes
        if lang == "kn":
            return "kn"
        if lang == "hi":
            return "hi"
        return "en"
    except Exception:
        # Fallback: simple Unicode range check
        for char in text:
            cp = ord(char)
            if 0x0C80 <= cp <= 0x0CFF:   # Kannada Unicode block
                return "kn"
            if 0x0900 <= cp <= 0x097F:   # Devanagari (Hindi) block
                return "hi"
        return "en"


# ── Translation ────────────────────────────────────────────────────────────────

def _translate_to_english(text: str, source_lang: str) -> str:
    """
    Translate text to English using deep_translator (Google Translate, free).
    Returns original text unchanged if already English or translation fails.
    """
    if source_lang == "en":
        return text
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source=source_lang, target="en").translate(text)
        return translated or text
    except Exception as exc:
        logger.warning("Translation failed (%s→en): %s", source_lang, exc)
        return text  # return original if translation fails


# ── Speech recognition ─────────────────────────────────────────────────────────

def _transcribe_audio(audio_bytes: bytes, language: str) -> tuple[str, float]:
    """
    Transcribe audio bytes using SpeechRecognition + Google Speech API (free tier).

    Returns (transcribed_text, confidence_estimate).
    The free Google endpoint does not return confidence scores, so we estimate:
      - 0.85 on success (plausible for clear speech)
      - 0.0 on failure
    """
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    bcp47 = LANG_TO_BCP47.get(language, "en-IN")

    # Write audio to a temp file — SpeechRecognition needs a file-like object
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with sr.AudioFile(tmp_path) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio, language=bcp47)
        return text, 0.85
    except sr.UnknownValueError:
        return "", 0.0
    except sr.RequestError as exc:
        raise RuntimeError(f"Google Speech API unavailable: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── Multi-language transcription orchestrator ──────────────────────────────────

def _try_all_languages(audio_bytes: bytes) -> tuple[str, str, float]:
    """
    Try transcription in all three supported languages and return the best result.
    Tries each language and picks the one that returns the longest non-empty text
    (a reasonable proxy for correctness when language is unknown).

    Returns (text, detected_lang, confidence).
    """
    best_text = ""
    best_lang = "en"
    best_conf = 0.0
    request_errors = []

    import speech_recognition as sr

    for lang in SUPPORTED_LANGS:
        try:
            text, conf = _transcribe_audio(audio_bytes, lang)
            if text and len(text) > len(best_text):
                best_text = text
                best_lang = lang
                best_conf = conf
        except sr.RequestError as exc:
            request_errors.append(str(exc))
        except Exception as exc:
            logger.debug("Transcription attempt for %s failed: %s", lang, exc)

    # Do not report a network outage as unintelligible speech.
    if not best_text and request_errors:
        raise RuntimeError(
            "Speech recognition could not reach Google. Check that the API "
            "container has internet access, or choose a language and try again."
        )

    return best_text, best_lang, best_conf


# ── Public API ─────────────────────────────────────────────────────────────────

async def transcribe(
    audio_base64: str,
    language_hint: Optional[str] = None,
) -> VoiceTranscript:
    """
    Transcribe base64-encoded audio and return a VoiceTranscript.

    Args:
        audio_base64: Base64-encoded WAV/MP3/OGG audio data.
        language_hint: Optional "en", "hi", or "kn". If provided, only that
                       language is attempted. If None, all three are tried.
    """
    try:
        audio_bytes = _decode_audio(audio_base64)
    except Exception as exc:
        return VoiceTranscript(
            original_text="", detected_language="en", language_name="English",
            english_text="", confidence=0.0,
            error=f"Audio decode error: {exc}",
        )

    try:
        if language_hint and language_hint in SUPPORTED_LANGS:
            # User specified a language — use it directly
            text, conf = _transcribe_audio(audio_bytes, language_hint)
            detected_lang = language_hint if text else "en"
        else:
            # Auto-detect by trying all languages
            text, detected_lang, conf = _try_all_languages(audio_bytes)
            # Refine detection using the text content
            if text:
                detected_lang = _detect_language(text)

        if not text:
            return VoiceTranscript(
                original_text="", detected_language="en", language_name="English",
                english_text="", confidence=0.0,
                error="Could not understand audio — please speak clearly and try again.",
            )

        english_text = _translate_to_english(text, detected_lang)

        return VoiceTranscript(
            original_text=text,
            detected_language=detected_lang,
            language_name=LANG_NAMES.get(detected_lang, "English"),
            english_text=english_text,
            confidence=conf,
        )

    except Exception as exc:
        logger.error("Transcription error: %s", exc)
        return VoiceTranscript(
            original_text="", detected_language="en", language_name="English",
            english_text="", confidence=0.0,
            error=str(exc),
        )

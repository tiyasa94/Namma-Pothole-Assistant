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
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
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

    # Streamlit records WAV at 16 kHz. Decode it and normalize quiet recordings
    # before sending them to the recognizer.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with sr.AudioFile(tmp_path) as source:
            audio = recognizer.record(source)
        audio = _normalize_audio(audio, sr)
        text = recognizer.recognize_google(audio, language=bcp47)
        return text, 0.85
    except sr.UnknownValueError:
        return "", 0.0
    except sr.RequestError as exc:
        raise RuntimeError(f"Google Speech API unavailable: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _normalize_audio(audio, speech_recognition_module):
    """Resample to a common format and amplify very quiet microphone input."""
    import numpy as np

    sample_rate = 16000
    raw = audio.get_raw_data(convert_rate=sample_rate, convert_width=2)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if samples.size == 0:
        return audio

    rms = float(np.sqrt(np.mean(samples * samples)))
    if 0 < rms < 3500:
        samples *= min(8.0, 3500.0 / rms)
    samples = np.clip(samples, -32768, 32767).astype("<i2")
    return speech_recognition_module.AudioData(samples.tobytes(), sample_rate, 2)


@lru_cache(maxsize=1)
def _get_local_whisper_model():
    """Load a small multilingual CPU model only when Google returns no text."""
    from faster_whisper import WhisperModel

    model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
    return WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        cpu_threads=max(1, min(4, os.cpu_count() or 1)),
    )


def _transcribe_with_local_whisper(
    audio_bytes: bytes,
    language_hint: Optional[str],
) -> tuple[str, str, float]:
    """Fallback ASR that works locally for English, Hindi, and Kannada."""
    model = _get_local_whisper_model()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(
            tmp_path,
            language=language_hint or None,
            beam_size=3,
            vad_filter=True,
            no_speech_threshold=0.6,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        detected_language = info.language or language_hint or "en"
        confidence = float(info.language_probability or 0.0)
        return text, detected_language, confidence
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

    if request_errors:
        logger.warning("Google speech recognition request errors: %s", request_errors)

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
        detected_lang = language_hint if language_hint in SUPPORTED_LANGS else "en"
        google_error = None
        try:
            if language_hint and language_hint in SUPPORTED_LANGS:
                text, conf = _transcribe_audio(audio_bytes, language_hint)
            else:
                text, detected_lang, conf = _try_all_languages(audio_bytes)
                if text:
                    detected_lang = _detect_language(text)
        except Exception as exc:
            text, conf = "", 0.0
            google_error = str(exc)
            logger.warning("Google transcription failed; trying local Whisper: %s", exc)

        if not text:
            try:
                text, detected_lang, conf = _transcribe_with_local_whisper(
                    audio_bytes,
                    language_hint if language_hint in SUPPORTED_LANGS else None,
                )
            except Exception as exc:
                logger.exception("Local Whisper fallback failed")
                reason = f"Google: {google_error}; " if google_error else ""
                return VoiceTranscript(
                    original_text="", detected_language="en", language_name="English",
                    english_text="", confidence=0.0,
                    error=(
                        f"Speech recognition could not transcribe this recording. {reason}"
                        f"Local transcription fallback failed: {exc}"
                    ),
                )

        if not text:
            return VoiceTranscript(
                original_text="", detected_language="en", language_name="English",
                english_text="", confidence=0.0,
                error="No speech was detected. Try speaking closer to the microphone and record again.",
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

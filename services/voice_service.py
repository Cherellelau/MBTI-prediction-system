import os
import re

from opencc import OpenCC
from faster_whisper import WhisperModel
from i18n import TRANSLATIONS
from services.prediction_service import translate_to_english


# ======================================
# Constants / global objects
# ======================================
cc_t2s = OpenCC("t2s")

WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "medium")  # base/small/medium
_whisper_model = None


# ======================================
# Language helpers
# ======================================
def get_lang_from_session(session_obj) -> str:
    lang = session_obj.get("lang", "EN")
    return lang if lang in TRANSLATIONS else "EN"


def t_voice(session_obj, key: str) -> str:
    lang = get_lang_from_session(session_obj)
    return TRANSLATIONS.get(lang, TRANSLATIONS["EN"]).get(key, key)


def normalize_voice_lang(lang: str | None) -> str:
    lang = (lang or "").strip().lower()

    if lang in ("en", "english"):
        return "en"
    if lang in ("ms", "malay", "bm", "bahasa melayu"):
        return "ms"
    if lang in ("zh", "zh-cn", "zh-tw", "chinese", "mandarin"):
        return "zh"

    return ""


def voice_msg(session_obj, reason_code: str, detected: str = "", selected: str = "") -> str:
    """
    Backend voice messages that follow current page language through session.
    """

    if reason_code == "supported_lang_only":
        return t_voice(session_obj, "voice_supported_lang_only")

    if reason_code == "unsupported_detected":
        base = t_voice(session_obj, "voice_supported_lang_only")
        if detected:
            return f"{base} ({t_voice(session_obj, 'test_detected_language')}: {detected.upper()})"
        return base

    if reason_code == "lang_mismatch":
        return t_voice(session_obj, "voice_lang_mismatch").format(
            selected=(selected or "").upper(),
            detected=(detected or "").upper()
        )

    return t_voice(session_obj, f"voice_{reason_code}")


# ======================================
# Whisper model
# ======================================
def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device="cpu",
            compute_type="int8"
        )
    return _whisper_model


# ======================================
# Speech-to-text
# ======================================
def speech_to_text_from_file(filepath: str, lang: str | None = None) -> tuple[str, str, str | None]:
    """
    Returns:
        transcript, detected_lang, selected_lang

    logic:
    1. If user selected a supported language, force Whisper to use it.
    2. Only use auto-detect when user did not choose a language.
    3. Never reject just because detected language differs.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Audio file not found: {filepath}")

    model = get_whisper_model()

    allowed_langs = {"en", "zh", "ms"}
    selected_lang = normalize_voice_lang(lang)
    if selected_lang not in allowed_langs:
        selected_lang = None

    # If user selected language, trust it and force transcription in that language
    if selected_lang:
        segments, info = model.transcribe(
            filepath,
            beam_size=5,
            vad_filter=True,
            task="transcribe",
            language=selected_lang
        )

        transcript = " ".join((segment.text or "").strip() for segment in segments).strip()
        detected_lang = normalize_voice_lang(
            (getattr(info, "language", "") or "").lower()
        ) or selected_lang

        return transcript, detected_lang, selected_lang

    # No selected language -> auto detect
    segments, info = model.transcribe(
        filepath,
        beam_size=5,
        vad_filter=True,
        task="transcribe"
    )

    transcript = " ".join((segment.text or "").strip() for segment in segments).strip()
    detected_lang = normalize_voice_lang(
        (getattr(info, "language", "") or "").lower()
    )

    return transcript, detected_lang, selected_lang


def convert_zh_to_simplified(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return cc_t2s.convert(text)


def process_transcript_for_prediction(transcript: str, detected_lang: str) -> tuple[str, str]:
    """
    Returns:
        display_transcript, final_english_text

    - If zh, convert transcript to simplified Chinese for display
    - Then translate to English for model use
    """
    detected_lang = normalize_voice_lang(detected_lang)
    transcript = (transcript or "").strip()

    if detected_lang == "zh" and transcript:
        transcript = convert_zh_to_simplified(transcript)

    transcript_en = translate_to_english(transcript, detected_lang)
    final_text = (transcript_en or transcript or "").strip()

    return transcript, final_text


# ======================================
# Validation for personality-related audio
# ======================================
def validate_voice_personality_content(text: str) -> tuple[bool, str]:
    """
    Returns: (is_valid, reason_code)

    reason_code:
    - empty
    - too_short
    - identity_only
    - greeting_only
    - background_only
    - insufficient
    - personality_related
    """
    t = (text or "").strip().lower()

    if not t:
        return False, "empty"

    words = [w for w in re.split(r"\s+", t) if w]
    word_count = len(words)

    if word_count < 4:
        return False, "too_short"

    # identity only
    identity_only_patterns = [
        r"^my name is\s+[a-z\s]+\.?$",
        r"^i am\s+[a-z\s]+\.?$",
        r"^i'm\s+[a-z\s]+\.?$"
    ]
    if any(re.match(p, t) for p in identity_only_patterns) and word_count <= 4:
        return False, "identity_only"

    # greeting only
    greeting_only_patterns = [
        r"^hello\.?$",
        r"^hi\.?$",
        r"^hey\.?$",
        r"^good morning\.?$",
        r"^good afternoon\.?$",
        r"^good evening\.?$"
    ]
    if any(re.match(p, t) for p in greeting_only_patterns):
        return False, "greeting_only"

    # weak background only
    weak_background_patterns = [
        r"\bi am \d{1,2} years old\b",
        r"\bi'm \d{1,2} years old\b",
        r"\bi study\b",
        r"\bi am studying\b",
        r"\bmy degree\b",
        r"\bmy course\b",
        r"\bcomputer science\b",
        r"\bengineering\b",
        r"\bbusiness\b",
        r"\bdata science\b",
        r"\bi am a student\b",
        r"\bi am currently studying\b"
    ]

    personality_keywords = [
        "i like", "i enjoy", "i prefer", "usually", "often", "always",
        "alone", "by myself", "friends", "team", "teams", "group",
        "group discussions", "people", "social", "talking to people",
        "plan", "planned", "planning", "schedule", "organized", "organised",
        "structure", "structured", "sudden changes",
        "logic", "facts", "efficient", "feelings", "affect others",
        "care about", "creative", "ideas", "imagine", "possibilities",
        "future outcomes", "carefully", "before i speak",
        "decision", "decisions", "behaviour", "behavior", "habit", "habits"
    ]

    has_weak_background = any(re.search(p, t) for p in weak_background_patterns)
    has_personality_clue = any(k in t for k in personality_keywords)

    if has_weak_background and not has_personality_clue:
        return False, "background_only"

    if has_personality_clue:
        return True, "personality_related"

    return False, "insufficient"

# ======================================
# Main high-level helper for routes
# ======================================
def transcribe_and_prepare_voice(filepath: str, selected_lang: str | None = None) -> dict:
    """
    High-level wrapper for routes.
    """
    allowed_langs = {"en", "zh", "ms"}
    selected_lang_norm = normalize_voice_lang(selected_lang)

    transcript, detected_lang, selected_lang_norm = speech_to_text_from_file(
        filepath,
        lang=selected_lang_norm
    )

    detected_lang = normalize_voice_lang(detected_lang)
    selected_lang_norm = normalize_voice_lang(selected_lang_norm)

    if detected_lang not in allowed_langs and not selected_lang_norm:
        return {
            "ok": False,
            "error_code": "unsupported_detected",
            "error": "",
            "transcript": "",
            "transcript_en": "",
            "detected_lang": "UNSUPPORTED",
            "selected_lang": (selected_lang_norm or "").upper(),
            "mismatch": False,
        }

    # Prefer selected language when user already chose one
    processing_lang = selected_lang_norm or detected_lang
    mismatch = bool(
        selected_lang_norm and detected_lang and selected_lang_norm != detected_lang
    )

    display_transcript, final_english_text = process_transcript_for_prediction(
        transcript,
        processing_lang
    )

    if not (display_transcript or "").strip():
        return {
            "ok": False,
            "error_code": "empty",
            "error": "",
            "transcript": "",
            "transcript_en": "",
            "detected_lang": (detected_lang or processing_lang or "").upper(),
            "selected_lang": (selected_lang_norm or "").upper(),
            "mismatch": mismatch,
        }

    return {
        "ok": True,
        "error_code": "",
        "error": "",
        "transcript": display_transcript,
        "transcript_en": final_english_text,
        "detected_lang": (detected_lang or processing_lang or "").upper(),
        "selected_lang": (selected_lang_norm or "").upper(),
        "mismatch": mismatch,
    }
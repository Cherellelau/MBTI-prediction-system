import os
import tempfile
import uuid
from functools import wraps

from flask import (
    Blueprint,
    request,
    jsonify,
    redirect,
    url_for,
    session,
    flash,
)

from werkzeug.utils import secure_filename

from i18n import TRANSLATIONS
from services.prediction_service import (
    ml_predict_top3_with_profile,
    store_pending_prediction,
    build_profile_context_for_prediction,
)

from services.voice_service import (
    normalize_voice_lang,
    voice_msg,
    transcribe_and_prepare_voice,
    validate_voice_personality_content,
)

voice_bp = Blueprint("voice", __name__)


# ======================================
# Helpers
# ======================================
def get_lang():
    lang = session.get("lang", "EN")
    return lang if lang in TRANSLATIONS else "EN"


def t_py(key: str) -> str:
    lang = get_lang()
    return TRANSLATIONS.get(lang, TRANSLATIONS["EN"]).get(key, key)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/voice/") or request.path == "/submit-voice":
                return jsonify({"error": t_py("msg_login_required")}), 401
            flash(t_py("msg_login_required"), "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper

def save_voice_prediction(text: str):
    user_id = session["user_id"]
    profile_context = build_profile_context_for_prediction(user_id)

    top3 = ml_predict_top3_with_profile(
        text,
        profile_context=profile_context
    )

    store_pending_prediction(
        top3,
        raw_text=text,
        profile_context=profile_context
    )
    
def detect_audio_suffix(filename: str) -> str:
    ext = os.path.splitext((filename or "").lower())[1]
    return ext if ext in ALLOWED_AUDIO_EXTENSIONS else ".webm"

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".webm"}


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ======================================
# Upload audio file
# ======================================
@voice_bp.post("/voice/upload")
@login_required
def voice_upload():
    if "audio" not in request.files:
        return jsonify({"error": t_py("msg_voice_missing")}), 400

    f = request.files["audio"]
    if f.filename == "":
        return jsonify({"error": t_py("msg_voice_missing")}), 400

    original_name = secure_filename(f.filename)
    ext = os.path.splitext(original_name)[1].lower()

    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({"error": t_py("msg_voice_invalid_file_type")}), 400

    filename = f"{session['user_id']}_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    f.save(save_path)

    return jsonify({"filename": filename}), 200


# ======================================
# AJAX transcription route
# ======================================
@voice_bp.post("/voice/transcribe", endpoint="voice_transcribe")
@login_required
def voice_transcribe():
    data = request.get_json(silent=True) or {}
    filename = data.get("filename")
    selected_lang = normalize_voice_lang(data.get("lang"))

    allowed_langs = {"en", "zh", "ms"}
    if selected_lang not in allowed_langs:
        selected_lang = None

    if not filename:
        return jsonify({"error": t_py("msg_voice_filename_required")}), 400

    audio_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(audio_path):
        return jsonify({"error": t_py("msg_voice_file_not_found")}), 404

    try:
        result = transcribe_and_prepare_voice(audio_path, selected_lang=selected_lang)

        if not result["ok"]:
            return jsonify({
                "error": voice_msg(
                    session,
                    result["error_code"],
                    detected=result["detected_lang"],
                    selected=result["selected_lang"]
                ),
                "detected_lang": result["detected_lang"],
                "selected_lang": result["selected_lang"],
                "transcript": result["transcript"],
                "transcript_en": result["transcript_en"],
                "mismatch": result["mismatch"]
            }), 400

        return jsonify({
            "transcript": result["transcript"],
            "detected_lang": result["detected_lang"],
            "selected_lang": result["selected_lang"],
            "transcript_en": result["transcript_en"],
            "warning": None,
            "mismatch": False
        }), 200

    except Exception as e:
        return jsonify({"error": t_py("msg_voice_failed").format(error=str(e))}), 500

    finally:
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass


# ======================================
# Submit already-transcribed voice text
# ======================================
@voice_bp.post("/voice/submit")
@login_required
def voice_submit():
    transcript = request.form.get("transcript", "").strip()
    transcript_en = request.form.get("transcript_en", "").strip()
    detected_lang = normalize_voice_lang(request.form.get("detected_lang"))

    final_text = (transcript_en or transcript).strip()

    if not final_text:
        flash(t_py("msg_voice_empty"), "error")
        return redirect(url_for("test.test"))

    if detected_lang not in {"en", "ms", "zh"}:
        flash(voice_msg(session, "supported_lang_only"), "error")
        return redirect(url_for("test.test"))

    is_valid, reason_code = validate_voice_personality_content(final_text)
    if not is_valid:
        flash(voice_msg(session, reason_code), "error")
        return redirect(url_for("test.test"))

    save_voice_prediction(final_text)
    return redirect(url_for("result.result_page"))


# ======================================
# Direct audio upload + process route
# ======================================
@voice_bp.post("/submit-voice")
@login_required
def submit_voice():
    audio = request.files.get("audio")
    if not audio:
        flash(t_py("msg_voice_missing"), "error")
        return redirect(url_for("test.test"))

    ext = os.path.splitext((audio.filename or "").lower())[1]
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        flash(t_py("msg_voice_invalid_file_type"), "error")
        return redirect(url_for("test.test"))

    suffix = detect_audio_suffix(audio.filename)
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            audio.save(tmp_path)

        result = transcribe_and_prepare_voice(tmp_path)

        if not result["ok"]:
            flash(
                voice_msg(
                    session,
                    result["error_code"],
                    detected=result["detected_lang"],
                    selected=result["selected_lang"]
                ),
                "error"
            )
            return redirect(url_for("test.test"))

        final_text = (result["transcript_en"] or result["transcript"] or "").strip()

        if not final_text:
            flash(t_py("msg_voice_empty"), "error")
            return redirect(url_for("test.test"))

        is_valid, reason_code = validate_voice_personality_content(final_text)
        if not is_valid:
            flash(voice_msg(session, reason_code), "error")
            return redirect(url_for("test.test"))

        save_voice_prediction(final_text)
        return redirect(url_for("result.result_page"))

    except Exception as e:
        flash(t_py("msg_voice_failed").format(error=str(e)), "error")
        return redirect(url_for("test.test"))

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

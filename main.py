import os

from flask import (
    Flask,
    session,
    request,
    redirect,
    url_for,
    has_request_context,
    render_template,
    flash,
)
from dotenv import load_dotenv

from i18n import TRANSLATIONS
from db import (
    init_db,
    get_user_by_id,
    update_user_language,
    list_careers_for_type,
    get_user_profile_by_user_id,
)

# Blueprints
from admin_routes import admin_bp
from routes.auth_routes import auth_bp
from routes.profile_routes import profile_bp
from routes.test_routes import test_bp
from routes.voice_routes import voice_bp
from routes.result_routes import result_bp
from routes.timeline_routes import timeline_bp

load_dotenv()

ALL_MBTI_TYPES = [a + b + c + d for a in "IE" for b in "NS" for c in "TF" for d in "JP"]
VALID_MBTI_TYPES = set(ALL_MBTI_TYPES)


def create_app():
    app = Flask(__name__)

    # ======================================
    # Basic Config
    # ======================================
    app.secret_key = os.environ.get("SECRET_KEY", "CHANGE_ME_TO_A_RANDOM_SECRET")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 8MB upload limit

    # ======================================
    # Language helpers
    # ======================================
    def get_lang():
        if not has_request_context():
            return "EN"

        lang = session.get("lang", "EN")
        return lang if lang in TRANSLATIONS else "EN"

    def t_py(key: str) -> str:
        lang = get_lang()
        return TRANSLATIONS.get(lang, TRANSLATIONS["EN"]).get(key, key)

    app.get_lang = get_lang
    app.t_py = t_py

    def is_profile_completed(user_id: int) -> bool:
        try:
            profile = get_user_profile_by_user_id(user_id)
            return bool(profile and int(profile.get("profileCompleted", 0) or 0) == 1)
        except Exception:
            return False

    # ======================================
    # Context processor
    # ======================================
    @app.context_processor
    def inject_t():
        lang = get_lang()

        def t(key: str):
            return TRANSLATIONS.get(lang, TRANSLATIONS["EN"]).get(key, key)

        is_admin = False
        uid = session.get("user_id")
        if uid:
            try:
                user = get_user_by_id(uid)
                if user:
                    user = dict(user)
                    is_admin = bool(int(user.get("isAdmin", 0)) == 1)
            except Exception:
                pass

        return {
            "t": t,
            "current_lang": lang,
            "is_admin": is_admin,
        }

    # ======================================
    # Access control
    # ======================================
    @app.before_request
    def require_completed_profile():
        endpoint = request.endpoint

        if not endpoint:
            return

        # Public/auth/common endpoints
        public_endpoints = {
            "auth.login",
            "auth.login_post",
            "auth.register",
            "auth.register_post",
            "auth.confirm_email",
            "auth.forgot_password",
            "auth.forgot_password_post",
            "auth.reset_password",
            "auth.reset_password_post",
            "auth.logout",
            "set_language",
            "static",
        }

        if endpoint in public_endpoints:
            return

        user_id = session.get("user_id")
        if not user_id:
            return

        try:
            user = get_user_by_id(user_id)
            user = dict(user) if user else None
        except Exception:
            user = None

        if not user:
            return

        profile_completed = is_profile_completed(user_id)
        is_admin = int(user.get("isAdmin", 0) or 0) == 1

        # ======================================
        # Pages allowed during onboarding
        # ======================================
        onboarding_endpoints = {
            "profile.profile_onboarding",
            "profile.profile_manual",
            "profile.profile_manual_post",
            "profile.upload_resume_page",
            "profile.upload_resume_post",
            "profile.capture_resume_page",
            "profile.capture_resume_post",
            "profile.preview_resume_text",
            "profile.parse_resume_profile_page",
            "profile.confirm_resume_profile_post",
        }

        # ======================================
        # Admin pages allowed WITHOUT profile
        # ======================================
        admin_allowed_without_profile = {
            # Scenario module
            "admin.scenario_list",
            "admin.scenario_new",
            "admin.scenario_edit",
            "admin.scenario_edit_save_all",
            "admin.option_edit",
            "admin.option_delete",
            "admin.scenario_delete",
            "admin.admin_translate",
            "admin.admin_translate_bulk",
            "admin.scenario_translate_save",

            # Career Recommendation module
            "admin.careers_list",
            "admin.careers_create",
            "admin.careers_edit",
            "admin.careers_update",
            "admin.careers_delete",

            # User Account Management module
            "admin.admin_users_list",
            "admin.admin_user_records",
            "admin.admin_reset_user_password",

            # Onboarding pages
            "profile.profile_onboarding",
            "profile.profile_manual",
            "profile.profile_manual_post",
            "profile.upload_resume_page",
            "profile.upload_resume_post",
            "profile.capture_resume_page",
            "profile.capture_resume_post",
            "profile.preview_resume_text",
            "profile.parse_resume_profile_page",
            "profile.confirm_resume_profile_post",

            # Common
            "auth.logout",
            "set_language",
            "static",
        }

        # ======================================
        # Admin logic
        # ======================================
        if is_admin:
            # only restrict admin if profile NOT completed
            if not profile_completed:
                if endpoint in admin_allowed_without_profile:
                    return
                flash(t_py("msg_complete_profile_first"), "warning")
                return redirect(url_for("profile.profile_onboarding"))

            # admin with completed profile = normal access
            return

        # ======================================
        # Normal user onboarding flow
        # ======================================
        if endpoint in onboarding_endpoints:
            return

        # ======================================
        # Normal user must complete profile first
        # ======================================
        if not profile_completed:
            flash(t_py("msg_complete_profile_first"), "warning")
            return redirect(url_for("profile.profile_onboarding"))

    # ======================================
    # Shared routes kept in main.py
    # ======================================
    @app.get("/")
    def home():
        if "user_id" in session:
            try:
                user = get_user_by_id(session["user_id"])
                user = dict(user) if user else None

                if user and int(user.get("isAdmin", 0) or 0) == 1:
                    if not is_profile_completed(session["user_id"]):
                        return redirect(url_for("profile.profile_onboarding"))
                    return redirect(url_for("profile.home_page"))

                if user and not is_profile_completed(session["user_id"]):
                    return redirect(url_for("profile.profile_onboarding"))

            except Exception:
                pass

            return redirect(url_for("profile.home_page"))

        return redirect(url_for("auth.login"))

    @app.post("/set-language")
    def set_language():
        lang = request.form.get("lang", "EN").strip().upper()
        if lang not in ["EN", "ZH", "BM"]:
            lang = "EN"

        session["lang"] = lang

        # clear scenario cache when language changes
        for k in [
            "scenario_snapshot",
            "scenario_qids",
            "scenario_gids",
            "scenario_answers",
            "scenario_idx",
            "scenario_snapshot_lang",
        ]:
            session.pop(k, None)

        session.modified = True

        if session.get("user_id"):
            try:
                user = get_user_by_id(session["user_id"])
                if user:
                    update_user_language(session["user_id"], lang)
            except Exception:
                pass

        next_url = request.form.get("next") or request.referrer or url_for("auth.login")
        return redirect(next_url)

    @app.get("/explore")
    def explore():
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return render_template("explore.html", types=ALL_MBTI_TYPES)

    @app.get("/type/<type_code>")
    def type_detail(type_code):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))

        type_code = (type_code or "").upper().strip()
        if type_code not in VALID_MBTI_TYPES:
            flash(t_py("msg_record_not_found"), "error")
            return redirect(url_for("explore"))

        lang = session.get("lang", "EN")
        careers = list_careers_for_type(type_code, lang=lang)
        return render_template("type_detail.html", type_code=type_code, careers=careers)

    # ======================================
    # Register blueprints
    # ======================================
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(result_bp)
    app.register_blueprint(timeline_bp)

    # ======================================
    # Initialize DB
    # ======================================
    init_db()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    current_app,
)
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from auth import hash_password, verify_password
from db import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    verify_user,
    update_user_password_hash,
    update_user_language,
    get_user_profile_by_user_id,
)
from i18n import TRANSLATIONS
from services.email_service import (
    send_confirm_email,
    send_password_reset_email,
)

auth_bp = Blueprint("auth", __name__)


def row_to_dict(row):
    return dict(row) if row is not None else None


def get_lang():
    lang = session.get("lang", "EN")
    return lang if lang in TRANSLATIONS else "EN"


def t_py(key: str) -> str:
    lang = get_lang()
    return TRANSLATIONS.get(lang, TRANSLATIONS["EN"]).get(key, key)


def get_confirm_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="email-confirm")


def get_reset_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="password-reset")


def get_user_by_email_dict(email: str):
    return row_to_dict(get_user_by_email((email or "").strip().lower()))


def get_user_by_id_dict(user_id: int):
    return row_to_dict(get_user_by_id(user_id))


def user_profile_completed(user_id: int) -> bool:
    profile = get_user_profile_by_user_id(user_id)
    return bool(profile and int(profile.get("profileCompleted", 0) or 0) == 1)


def is_valid_lang(lang: str) -> bool:
    return (lang or "").upper() in {"EN", "ZH", "BM"}


def validate_password_pair(password: str, confirm_password: str):
    if len(password) < 6 or len(password) > 8:
        return t_py("msg_pw_len_6_8")
    if password != confirm_password:
        return t_py("msg_pw_not_match")
    return None


def is_matching_user_email(user: dict, email: str) -> bool:
    return bool(user and (user.get("email") or "").lower() == (email or "").lower())


def decode_token_or_none(serializer, token: str, max_age: int):
    try:
        return serializer.loads(token, max_age=max_age), None
    except SignatureExpired:
        return None, "expired"
    except BadSignature:
        return None, "invalid"


def flash_token_error(kind: str, expired_key: str, invalid_key: str):
    if kind == "expired":
        flash(t_py(expired_key), "error")
    else:
        flash(t_py(invalid_key), "error")


@auth_bp.get("/login")
def login():
    return render_template("login.html")


@auth_bp.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email_dict(email)
    if not user:
        flash(t_py("msg_user_not_found"), "error")
        return redirect(url_for("auth.login"))

    if not verify_password(password, user["passwordHash"]):
        flash(t_py("msg_wrong_password"), "error")
        return redirect(url_for("auth.login"))

    if int(user.get("isVerified", 0)) != 1:
        flash(t_py("msg_account_not_verified"), "warning")
        return redirect(url_for("auth.login"))

    session["user_id"] = int(user["userID"])
    session["email"] = user.get("email", "")
    session["name"] = user.get("name", "") or ""

    db_lang = (
        (user.get("preferredLanguage") or "EN").upper()
        if "preferredLanguage" in user.keys()
        else "EN"
    )

    chosen_lang = (session.get("lang") or "").upper()
    if is_valid_lang(chosen_lang):
        session["lang"] = chosen_lang
        try:
            update_user_language(session["user_id"], chosen_lang)
        except Exception:
            pass
    else:
        session["lang"] = db_lang

    if not user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.profile_onboarding"))

    flash(t_py("msg_login_success"), "success")
    return redirect(url_for("profile.home_page"))


@auth_bp.get("/register")
def register():
    return render_template("register.html")


@auth_bp.post("/register")
def register_post():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    pw = request.form.get("password", "")
    pw2 = request.form.get("confirm_password", "")

    if not name:
        flash(t_py("msg_name_required"), "error")
        return redirect(url_for("auth.register"))

    if not email or not pw:
        flash(t_py("msg_email_pw_required"), "error")
        return redirect(url_for("auth.register"))

    pw_error = validate_password_pair(pw, pw2)
    if pw_error:
        flash(pw_error, "error")
        return redirect(url_for("auth.register"))

    try:
        user_id = create_user(email, name, hash_password(pw))

        token = get_confirm_serializer().dumps({"user_id": user_id, "email": email})
        confirm_url = url_for("auth.confirm_email", token=token, _external=True)

        send_confirm_email(email, confirm_url, lang=get_lang())

        flash(t_py("msg_verify_sent"), "success")
        return redirect(url_for("auth.login"))

    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg or "constraint" in msg:
            flash(t_py("msg_email_exists"), "error")
        else:
            flash(t_py("msg_register_failed").format(error=str(e)), "error")
        return redirect(url_for("auth.register"))


@auth_bp.get("/confirm/<token>")
def confirm_email(token):
    data, err = decode_token_or_none(get_confirm_serializer(), token, 60 * 60 * 24)
    if err:
        flash_token_error(err, "msg_confirm_expired", "msg_confirm_invalid")
        return redirect(url_for("auth.login"))

    user_id = int(data.get("user_id"))
    email = (data.get("email") or "").lower()

    user = get_user_by_id_dict(user_id)
    if not is_matching_user_email(user, email):
        flash(t_py("msg_confirm_invalid"), "error")
        return redirect(url_for("auth.login"))

    if int(user.get("isVerified", 0)) == 1:
        flash(t_py("msg_already_verified"), "success")
        return redirect(url_for("auth.login"))

    verify_user(user_id)
    flash(t_py("msg_confirm_success"), "success")
    return redirect(url_for("auth.login"))


@auth_bp.get("/forgot-password", endpoint="forgot_password")
def forgot_password():
    return render_template("forgot_password.html")


@auth_bp.post("/forgot-password")
def forgot_password_post():
    email = (request.form.get("email") or "").strip().lower()
    success_msg = t_py("msg_reset_link_sent_generic")

    if not email:
        flash(t_py("msg_email_required"), "error")
        return redirect(url_for("auth.forgot_password"))

    user = get_user_by_email_dict(email)
    if user:
        token = get_reset_serializer().dumps(
            {"user_id": int(user["userID"]), "email": email}
        )
        reset_url = url_for("auth.reset_password", token=token, _external=True)
        send_password_reset_email(email, reset_url, lang=get_lang())

    flash(success_msg, "success")
    return redirect(url_for("auth.login"))


@auth_bp.get("/reset-password/<token>")
def reset_password(token):
    data, err = decode_token_or_none(get_reset_serializer(), token, 60 * 30)
    if err:
        flash_token_error(err, "msg_reset_link_expired", "msg_reset_link_invalid")
        return redirect(url_for("auth.forgot_password"))

    email = (data.get("email") or "").lower()
    return render_template("reset_password.html", token=token, email=email)


@auth_bp.post("/reset-password/<token>")
def reset_password_post(token):
    data, err = decode_token_or_none(get_reset_serializer(), token, 60 * 30)
    if err:
        flash_token_error(err, "msg_reset_link_expired", "msg_reset_link_invalid")
        return redirect(url_for("auth.forgot_password"))

    user_id = int(data.get("user_id"))
    email = (data.get("email") or "").lower()

    user = get_user_by_id_dict(user_id)
    if not is_matching_user_email(user, email):
        flash(t_py("msg_reset_link_invalid"), "error")
        return redirect(url_for("auth.forgot_password"))

    new_pw = (request.form.get("new_password") or "").strip()
    confirm_pw = (request.form.get("confirm_password") or "").strip()

    pw_error = validate_password_pair(new_pw, confirm_pw)
    if pw_error:
        flash(pw_error, "error")
        return redirect(url_for("auth.reset_password", token=token))

    update_user_password_hash(user_id, hash_password(new_pw))
    flash(t_py("msg_password_reset_success"), "success")
    return redirect(url_for("auth.login"))


@auth_bp.post("/logout")
def logout():
    session.clear()
    flash(t_py("msg_logged_out"), "success")
    return redirect(url_for("auth.login"))

import json
from datetime import datetime
from functools import wraps
from io import BytesIO

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_file,
)

import db
from db import (
    create_result,
    get_result_for_user,
    delete_result,
    list_careers_for_type,
    list_options_for_question,
    build_profile_snapshot,
    build_context_summary,
)

from i18n import TRANSLATIONS
from services.email_service import send_email_simple
from services.prediction_service import (
    get_pending_prediction,
    clear_pending_prediction,
    get_confidence_for_type,
    VALID_MBTI_TYPES,
    score_side,
)
from services.pdf_service import (
    get_mbti_profile_from_translations,
    build_result_pdf_bytes,
)

result_bp = Blueprint("result", __name__)


# ======================================
# Helpers
# ======================================
def row_to_dict(row):
    return dict(row) if row is not None else None


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
            flash(t_py("msg_login_required"), "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def get_pending_or_none():
    return get_pending_prediction()


def get_session_email():
    return (session.get("email") or "").strip().lower()


def parse_result_payload(raw_text: str):
    raw = (raw_text or "").strip()
    if not (raw.startswith("{") and raw.endswith("}")):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def get_chosen_type_and_confidence(pending: dict, form) -> tuple[str, float | None, str | None]:
    chosen = (form.get("chosen_type") or "").strip().upper()
    if not chosen:
        return "", None, "missing"

    conf = get_confidence_for_type(pending.get("top3", []), chosen)
    if conf is None:
        return chosen, None, "invalid"

    return chosen, conf, None


def build_pending_raw_text(pending: dict, user_id: int) -> tuple[str, dict, str]:
    profile_snapshot = build_profile_snapshot(user_id)
    context_summary = build_context_summary(profile_snapshot)
    profile_context = pending.get("profile_context") or {}

    if pending.get("raw_payload"):
        raw_text = json.dumps(pending["raw_payload"], ensure_ascii=False)
    else:
        user_input = (pending.get("raw_text") or "").strip()
        if user_input:
            raw_text = json.dumps({
                "kind": "text",
                "input": user_input,
                "profile_used": bool(profile_context.get("profileCompleted")),
                "profile_context": profile_context
            }, ensure_ascii=False)
        else:
            raw_text = ""

    return raw_text, profile_snapshot, context_summary


def build_saved_result_text_context(raw_text: str, lang: str) -> tuple[str, str]:
    user_input_text = ""
    scenario_summary = ""

    payload = parse_result_payload(raw_text)
    if isinstance(payload, dict) and payload.get("kind") == "scenario":
        try:
            scenario_summary = build_scenario_display(payload, lang)
        except Exception:
            scenario_summary = ""
    else:
        user_input_text = (raw_text or "").strip()

    return user_input_text, scenario_summary


def build_pending_result_text_context(pending: dict, lang: str) -> tuple[str, str]:
    user_input_text = (pending.get("raw_text") or "").strip() if pending.get("raw_text") else ""
    scenario_summary = ""

    raw_payload = pending.get("raw_payload")
    if isinstance(raw_payload, dict) and raw_payload.get("kind") == "scenario":
        try:
            scenario_summary = build_scenario_display(raw_payload, lang)
        except Exception:
            scenario_summary = ""
            user_input_text = ""

    return user_input_text, scenario_summary


def build_pdf_context_from_pending(pending: dict, chosen: str, conf: float, lang: str) -> dict:
    mbti_profile = get_mbti_profile_from_translations(chosen, lang)
    careers = list_careers_for_type(chosen, lang=lang)
    user_input_text, scenario_summary = build_pending_result_text_context(pending, lang)

    return {
        "type_code": chosen,
        "confidence": conf,
        "scenario_summary_text": scenario_summary,
        "careers": careers,
        "mbti_profile": mbti_profile,
        "user_input_text": user_input_text,
        "lang": lang,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def build_pdf_context_from_saved_row(row: dict, lang: str) -> dict:
    type_code = (row.get("typeCode") or "").upper()
    confidence = row.get("confidenceScore") or 0
    created_at = row.get("createdAt") or ""

    raw_text = (row.get("rawText") or "").strip()
    user_input_text, scenario_summary = build_saved_result_text_context(raw_text, lang)

    careers = list_careers_for_type(type_code, lang=lang)
    mbti_profile = get_mbti_profile_from_translations(type_code, lang)

    return {
        "type_code": type_code,
        "confidence": confidence,
        "scenario_summary_text": scenario_summary,
        "careers": careers,
        "mbti_profile": mbti_profile,
        "user_input_text": user_input_text,
        "lang": lang,
        "created_at": created_at,
    }


def build_scenario_display(payload: dict, lang: str) -> str:
    """
    Rebuild a scenario test summary in the user's preferred language.

    Expected NEW payload format:
      payload = {
        "kind": "scenario",
        "answers": [{"groupID": 101, "optionKey": "A"}, ...],
        "scores": {"EI": 2, "SN": -2, "TF": 0, "JP": 2}
      }

    Backward compatibility OLD payload format:
      payload = {
        "kind": "scenario",
        "answers": [{"questionID": 12, "optionID": 55}, ...],
        "scores": {...}
      }
    """
    lang = (lang or "EN").upper()
    if lang not in ("EN", "ZH", "BM"):
        lang = "EN"

    lines = []
    lines.append(t_py("scenario_summary_title"))
    lines.append(t_py("scenario_your_answers"))

    answers = payload.get("answers") or []

    # NEW format: groupID + optionKey
    if answers and ("groupID" in answers[0] or "optionKey" in answers[0]):
        for i, a in enumerate(answers, start=1):
            try:
                gid = int(a.get("groupID", 0))
            except Exception:
                gid = 0

            key = (a.get("optionKey") or "").strip().upper()
            if key not in ("A", "B", "C", "D"):
                key = "?"

            if gid <= 0:
                lines.append(f"Q{i}: {key} - ")
                continue

            q_lang = db.admin_get_question_by_group_lang(gid, lang)
            q_en = db.admin_get_question_by_group_lang(gid, "EN")
            chosen_q = q_lang or q_en
            if not chosen_q:
                lines.append(f"Q{i}: {key} - ")
                continue

            qid_lang = int(chosen_q["questionID"])
            opts = [dict(o) for o in list_options_for_question(qid_lang, lang)]

            otext = ""
            for o in opts:
                if (o.get("optionKey") or "").strip().upper() == key:
                    otext = (o.get("optionText") or "")
                    break

            lines.append(f"Q{i}: {key} - {otext}")

    # OLD format: questionID + optionID
    else:
        for i, a in enumerate(answers, start=1):
            try:
                qid_saved = int(a.get("questionID", 0))
                oid_saved = int(a.get("optionID", 0))
            except Exception:
                qid_saved, oid_saved = 0, 0

            if qid_saved <= 0 or oid_saved <= 0:
                lines.append(f"Q{i}: ? - ")
                continue

            group_id = None
            try:
                qrow = db.admin_get_question(qid_saved)
                if qrow:
                    group_id = int(qrow.get("groupID") or qid_saved)
            except Exception:
                group_id = qid_saved

            saved_key = None
            try:
                en_q = db.admin_get_question_by_group_lang(int(group_id), "EN")
                if en_q:
                    en_qid = int(en_q["questionID"])
                    en_opts = [dict(o) for o in list_options_for_question(en_qid, "EN")]
                    for o in en_opts:
                        if int(o.get("optionID", 0)) == oid_saved:
                            saved_key = (o.get("optionKey") or "").strip().upper()
                            break
            except Exception:
                saved_key = None

            key = saved_key or "?"

            q_lang = db.admin_get_question_by_group_lang(int(group_id), lang)
            q_en = db.admin_get_question_by_group_lang(int(group_id), "EN")
            chosen_q = q_lang or q_en
            if not chosen_q:
                lines.append(f"Q{i}: {key} - ")
                continue

            qid_lang = int(chosen_q["questionID"])
            opts = [dict(o) for o in list_options_for_question(qid_lang, lang)]

            otext = ""
            if saved_key:
                for o in opts:
                    if (o.get("optionKey") or "").strip().upper() == saved_key:
                        otext = (o.get("optionText") or "")
                        break

            lines.append(f"Q{i}: {key} - {otext}")

    s = payload.get("scores") or {}
    try:
        ei_v = int(s.get("EI", 0))
        sn_v = int(s.get("SN", 0))
        tf_v = int(s.get("TF", 0))
        jp_v = int(s.get("JP", 0))
    except Exception:
        ei_v = sn_v = tf_v = jp_v = 0

    lines.append("")
    lines.append(t_py("score_breakdown_title"))
    lines.append(f"EI: {ei_v} ({t_py('leans')} {score_side('EI', ei_v)})")
    lines.append(f"SN: {sn_v} ({t_py('leans')} {score_side('SN', sn_v)})")
    lines.append(f"TF: {tf_v} ({t_py('leans')} {score_side('TF', tf_v)})")
    lines.append(f"JP: {jp_v} ({t_py('leans')} {score_side('JP', jp_v)})")

    return "\n".join(lines)


# ======================================
# Result page
# ======================================
@result_bp.get("/result")
@login_required
def result_page():
    pending = get_pending_or_none()
    if not pending:
        flash(t_py("msg_no_pending"), "warning")
        return redirect(url_for("test.test"))

    return render_template("result.html", pending=pending)


@result_bp.post("/result/confirm")
@login_required
def confirm_result():
    pending = get_pending_or_none()
    if not pending:
        flash(t_py("msg_no_pending"), "warning")
        return redirect(url_for("test.test"))

    chosen, confidence, err = get_chosen_type_and_confidence(pending, request.form)
    if err == "missing":
        flash(t_py("msg_choose_one"), "error")
        return redirect(url_for("result.result_page"))
    if err == "invalid":
        flash(t_py("msg_choose_one"), "error")
        return redirect(url_for("result.result_page"))

    raw_text, profile_snapshot, context_summary = build_pending_raw_text(
        pending,
        session["user_id"]
    )

    create_result(
        user_id=session["user_id"],
        type_code=chosen,
        confidence=confidence,
        raw_text=raw_text,
        profile_snapshot=profile_snapshot,
        context_summary=context_summary
    )

    clear_pending_prediction()
    flash(
        t_py("msg_saved_predicted").format(type_code=chosen, conf=confidence),
        "success"
    )

    return redirect(url_for("result.career_result", type_code=chosen))


@result_bp.get("/career/<type_code>")
@login_required
def career_result(type_code):
    type_code = (type_code or "").upper().strip()
    if type_code not in VALID_MBTI_TYPES:
        flash(t_py("msg_record_not_found"), "error")
        return redirect(url_for("test.test"))

    lang = session.get("lang", "EN")
    careers = list_careers_for_type(type_code, lang=lang)
    return render_template("career_result.html", type_code=type_code, careers=careers)


# ======================================
# Email result summary
# ======================================
@result_bp.post("/result/email", endpoint="send_result_email")
@login_required
def send_result_email():
    pending = get_pending_or_none()
    if not pending:
        flash(t_py("msg_no_pending"), "warning")
        return redirect(url_for("test.test"))

    chosen, conf, err = get_chosen_type_and_confidence(pending, request.form)
    if err == "missing":
        flash(t_py("msg_choose_one"), "error")
        return redirect(url_for("result.result_page"))
    if err == "invalid":
        flash(t_py("msg_choose_one"), "error")
        return redirect(url_for("result.result_page"))

    to_email = get_session_email()
    if not to_email:
        flash(t_py("msg_email_required"), "error")
        return redirect(url_for("result.result_page"))

    raw_text = (pending.get("raw_text") or "").strip()
    top3_list = pending.get("top3", [])

    subject = f"Your MBTI Result: {chosen}"

    lines = []
    lines.append("MBTI Result Summary")
    lines.append("=" * 20)
    lines.append(f"Selected Type: {chosen}")
    lines.append(f"Confidence: {round(float(conf) * 100)}%")
    lines.append("")
    lines.append("Top 3 Predictions:")

    for i, it in enumerate(top3_list, start=1):
        tc = (it.get("typeCode") or "").upper()
        cf = it.get("confidence")
        try:
            cf_pct = f"{round(float(cf) * 100)}%"
        except Exception:
            cf_pct = str(cf)
        lines.append(f"{i}. {tc}  (confidence: {cf_pct})")

    if raw_text:
        lines.append("")
        lines.append("Your Input / Summary:")
        lines.append(raw_text)

    body = "\n".join(lines)

    ok, msg = send_email_simple(
        to_email=to_email,
        subject=subject,
        body=body,
        attachment_bytes=None
    )

    flash(msg if not ok else t_py("msg_email_sent_success"), "success" if ok else "error")
    return redirect(url_for("result.result_page"))


@result_bp.post("/result/email-pdf", endpoint="send_result_email_pdf")
@login_required
def send_result_email_pdf():
    pending = get_pending_or_none()
    if not pending:
        flash(t_py("msg_no_pending"), "warning")
        return redirect(url_for("test.test"))

    chosen, conf, err = get_chosen_type_and_confidence(pending, request.form)
    if err == "missing":
        flash(t_py("msg_choose_one"), "error")
        return redirect(url_for("result.result_page"))
    if err == "invalid":
        flash(t_py("msg_choose_one"), "error")
        return redirect(url_for("result.result_page"))

    to_email = get_session_email()
    if not to_email:
        flash(t_py("msg_email_required"), "error")
        return redirect(url_for("result.result_page"))

    lang = session.get("lang", "EN").upper()
    pdf_context = build_pdf_context_from_pending(pending, chosen, conf, lang)

    pdf_bytes = build_result_pdf_bytes(
        type_code=pdf_context["type_code"],
        confidence=pdf_context["confidence"],
        scenario_summary_text=pdf_context["scenario_summary_text"],
        careers=pdf_context["careers"],
        mbti_profile=pdf_context["mbti_profile"],
        user_input_text=pdf_context["user_input_text"],
        lang=pdf_context["lang"],
        created_at=pdf_context["created_at"]
    )

    subject = f"Your MBTI Result (PDF): {chosen}"
    body = "Attached is your MBTI result report including career recommendations."

    ok, msg = send_email_simple(
        to_email=to_email,
        subject=subject,
        body=body,
        attachment_bytes=pdf_bytes,
        attachment_filename=f"MBTI_Result_{chosen}.pdf"
    )

    flash(msg if not ok else t_py("msg_email_sent_success"), "success" if ok else "error")
    return redirect(url_for("result.result_page"))


# ======================================
# View saved result
# ======================================
@result_bp.get("/result/<int:result_id>/view", endpoint="result_view")
@login_required
def result_view(result_id):
    row = get_result_for_user(result_id, session["user_id"])
    if not row:
        flash(t_py("msg_record_not_found"), "error")
        return redirect(url_for("timeline.timeline"))

    row = dict(row)
    lang = session.get("lang", "EN")
    raw = (row.get("rawText") or "").strip()

    parsed_answers = []
    score_breakdown = None
    test_method = "text"

    payload = parse_result_payload(raw)
    if isinstance(payload, dict) and payload.get("kind") == "scenario":
        try:
            test_method = "scenario"
            row["rawText"] = build_scenario_display(payload, lang)

            answers = payload.get("answers") or []
            for i, a in enumerate(answers, start=1):
                key = (a.get("optionKey") or "").strip().upper()
                gid = int(a.get("groupID", 0) or 0)
                text = ""

                if gid > 0 and key in ("A", "B", "C", "D"):
                    q_lang = db.admin_get_question_by_group_lang(gid, lang)
                    q_en = db.admin_get_question_by_group_lang(gid, "EN")
                    chosen_q = q_lang or q_en

                    if chosen_q:
                        qid_lang = int(chosen_q["questionID"])
                        opts = [dict(o) for o in list_options_for_question(qid_lang, lang)]
                        for o in opts:
                            if (o.get("optionKey") or "").strip().upper() == key:
                                text = (o.get("optionText") or "").strip()
                                break

                parsed_answers.append({
                    "num": i,
                    "letter": key or "?",
                    "text": text or "-"
                })

            s = payload.get("scores") or {}
            ei_v = int(s.get("EI", 0))
            sn_v = int(s.get("SN", 0))
            tf_v = int(s.get("TF", 0))
            jp_v = int(s.get("JP", 0))

            score_breakdown = {
                "EI": {"value": ei_v, "side": score_side("EI", ei_v)},
                "SN": {"value": sn_v, "side": score_side("SN", sn_v)},
                "TF": {"value": tf_v, "side": score_side("TF", tf_v)},
                "JP": {"value": jp_v, "side": score_side("JP", jp_v)},
            }
        except Exception:
            parsed_answers = []
            score_breakdown = None
    else:
        test_method = "voice_or_text"

    return render_template(
        "view_result.html",
        row=row,
        parsed_answers=parsed_answers,
        score_breakdown=score_breakdown,
        test_method=test_method
    )


# ======================================
# Download saved result PDF
# ======================================
@result_bp.get("/result/<int:result_id>/download-pdf", endpoint="download_result_pdf")
@login_required
def download_result_pdf(result_id):
    row = get_result_for_user(result_id, session["user_id"])
    if not row:
        flash(t_py("msg_record_not_found"), "error")
        return redirect(url_for("timeline.timeline"))

    row = dict(row)
    lang = session.get("lang", "EN").upper()
    pdf_context = build_pdf_context_from_saved_row(row, lang)

    pdf_bytes = build_result_pdf_bytes(
        type_code=pdf_context["type_code"],
        confidence=pdf_context["confidence"],
        scenario_summary_text=pdf_context["scenario_summary_text"],
        careers=pdf_context["careers"],
        mbti_profile=pdf_context["mbti_profile"],
        user_input_text=pdf_context["user_input_text"],
        lang=pdf_context["lang"],
        created_at=pdf_context["created_at"]
    )

    return send_file(
        BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=f"MBTI_Result_{pdf_context['type_code']}_{result_id}.pdf",
        mimetype="application/pdf"
    )


# ======================================
# JSON endpoint
# ======================================
@result_bp.get("/result/<int:result_id>/json", endpoint="result_json")
@login_required
def result_json(result_id):
    r = get_result_for_user(result_id, session["user_id"])
    if not r:
        return jsonify({"error": t_py("msg_record_not_found")}), 404

    r = dict(r)
    return jsonify({
        "resultID": r.get("resultID"),
        "typeCode": r.get("typeCode"),
        "confidenceScore": r.get("confidenceScore"),
        "rawText": r.get("rawText"),
        "createdAt": r.get("createdAt"),
        "fullUrl": url_for("result.result_view", result_id=result_id, _external=True)
    })


# ======================================
# Delete saved result
# ======================================
@result_bp.post("/result/<int:result_id>/delete")
@login_required
def delete_result_post(result_id):
    delete_result(result_id, session["user_id"])
    flash(t_py("msg_deleted"), "success")
    return redirect(url_for("timeline.timeline"))
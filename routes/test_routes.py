from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

from db import (
    get_user_profile_by_user_id,
    list_scenario_questions,
    list_options_for_question,
)
from i18n import TRANSLATIONS
from services.prediction_service import (
    store_pending_prediction,
    scores_to_mbti,
    confidence_from_scores,
    mutate_mbti_one_step,
    option_letter_from_index,
    build_profile_context_for_prediction,
    score_profile_mbti,
    combine_profile_with_dimension_scores,
)

test_bp = Blueprint("test", __name__)


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


def user_profile_completed(user_id: int) -> bool:
    profile = get_user_profile_by_user_id(user_id)
    if profile is None:
        return False

    try:
        profile = dict(profile)
    except Exception:
        pass

    return bool(profile and int(profile.get("profileCompleted", 0) or 0) == 1)


# ======================================
# Main test entry
# ======================================
@test_bp.get("/test")
@login_required
def test():
    if not user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.profile_manual"))

    return render_template("test.html")


# ======================================
# Scenario helpers
# ======================================
def predict_top3_from_snapshot(snapshot: list[dict], answers: dict, profile_context: dict | None = None) -> tuple[list[tuple[str, float]], dict]:
    ei = sn = tf = jp = 0
    raw_answers: list[dict] = []

    for q in (snapshot or []):
        qid = int(q.get("questionID", 0))
        if not qid:
            continue

        gid = int(q.get("groupID") or qid)

        oid = answers.get(str(qid))
        if oid is None:
            continue

        try:
            oid = int(oid)
        except Exception:
            continue

        chosen_opt = None
        chosen_idx = -1

        for idx, o in enumerate(q.get("options") or []):
            try:
                if int(o.get("optionID")) == oid:
                    chosen_opt = o
                    chosen_idx = idx
                    break
            except Exception:
                continue

        if not chosen_opt:
            continue

        ei += int(chosen_opt.get("EIScore", 0) or 0)
        sn += int(chosen_opt.get("SNScore", 0) or 0)
        tf += int(chosen_opt.get("TFScore", 0) or 0)
        jp += int(chosen_opt.get("JPScore", 0) or 0)

        key = (chosen_opt.get("optionKey") or "").strip().upper()
        if key not in ("A", "B", "C", "D"):
            key = option_letter_from_index(chosen_idx)

        raw_answers.append({
            "groupID": gid,
            "optionKey": key
        })

    profile_scores = score_profile_mbti(profile_context)
    combined_scores = combine_profile_with_dimension_scores(
        {
            "EI": ei,
            "SN": sn,
            "TF": tf,
            "JP": jp,
        },
        profile_scores,
        profile_weight=0.4
    )

    ei = combined_scores["EI"]
    sn = combined_scores["SN"]
    tf = combined_scores["TF"]
    jp = combined_scores["JP"]

    t1 = scores_to_mbti(ei, sn, tf, jp)
    c1 = confidence_from_scores(ei, sn, tf, jp)

    t2 = mutate_mbti_one_step(t1)
    t3 = mutate_mbti_one_step(t2)

    uniq = []
    for t in [t1, t2, t3]:
        if t not in uniq:
            uniq.append(t)

    while len(uniq) < 3:
        nxt = mutate_mbti_one_step(uniq[-1])
        if nxt not in uniq:
            uniq.append(nxt)

    c2 = round(max(0.45, c1 - 0.12), 2)
    c3 = round(max(0.40, c2 - 0.08), 2)

    top3 = [(uniq[0], c1), (uniq[1], c2), (uniq[2], c3)]
    top3.sort(key=lambda x: x[1], reverse=True)

    raw_payload = {
        "kind": "scenario",
        "answers": raw_answers,
        "scores": {
            "EI": ei,
            "SN": sn,
            "TF": tf,
            "JP": jp
        },
        "profile_used": bool(profile_context and profile_context.get("profileCompleted")),
        "profile_scores": profile_scores
    }

    return top3, raw_payload


# ======================================
# Scenario start
# ======================================
@test_bp.get("/scenario")
@login_required
def scenario_start():
    if not user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.profile_manual"))

    lang = session.get("lang", "EN").upper()

    for k in [
        "scenario_qids",
        "scenario_answers",
        "scenario_idx",
        "scenario_snapshot_lang"
    ]:
        session.pop(k, None)

    qs = [dict(q) for q in list_scenario_questions(lang=lang)]
    if not qs:
        flash(t_py("scenario_no_questions") if t_py("scenario_no_questions") != "scenario_no_questions" else "No scenario questions found in DB.", "error")
        return redirect(url_for("profile.home_page"))

    session["scenario_qids"] = [int(q["questionID"]) for q in qs]
    session["scenario_snapshot_lang"] = lang
    session["scenario_idx"] = 0
    session["scenario_answers"] = {}
    session.modified = True

    return redirect(url_for("test.scenario_question", idx=0))


# ======================================
# Scenario question page
# ======================================
@test_bp.get("/scenario/<int:idx>")
@login_required
def scenario_question(idx: int):
    lang = session.get("lang", "EN").upper()
    if session.get("scenario_snapshot_lang") != lang:
        return redirect(url_for("test.scenario_start"))

    qids = session.get("scenario_qids") or []
    if not qids:
        return redirect(url_for("test.scenario_start"))

    if idx < 0 or idx >= len(qids):
        return redirect(url_for("test.scenario_preview"))

    qid = int(qids[idx])

    qs = [dict(q) for q in list_scenario_questions(lang=lang)]
    item = next((q for q in qs if int(q["questionID"]) == qid), None)
    if not item:
        return redirect(url_for("test.scenario_start"))

    options = [dict(o) for o in list_options_for_question(qid, lang)]
    selected = (session.get("scenario_answers") or {}).get(str(qid))

    return_to_review = request.args.get("return_to_review", "0") == "1"

    return render_template(
        "scenario.html",
        q=item,
        options=options,
        idx=idx,
        total=len(qids),
        selected=selected,
        return_to_review=return_to_review
    )


@test_bp.get("/scenario/back/<int:idx>")
@login_required
def scenario_back(idx: int):
    prev_idx = idx - 1
    if prev_idx < 0:
        return redirect(url_for("test.scenario_start"))
    return redirect(url_for("test.scenario_question", idx=prev_idx))


# ======================================
# Save scenario answer
# ======================================
@test_bp.post("/scenario/answer")
@login_required
def scenario_answer():
    qid = request.form.get("question_id", "").strip()
    oid = request.form.get("option_id", "").strip()
    idx = int(request.form.get("idx", "0"))
    return_to_review = request.form.get("return_to_review", "0") == "1"

    if not qid or not oid:
        flash(t_py("scenario_choose_one"), "error")
        return redirect(url_for("test.scenario_question", idx=idx))

    answers = session.get("scenario_answers") or {}
    answers[str(qid)] = int(oid)
    session["scenario_answers"] = answers
    session["scenario_idx"] = idx
    session.modified = True

    qids = session.get("scenario_qids") or []
    next_idx = idx + 1

    if return_to_review:
        return redirect(url_for("test.scenario_preview"))

    if next_idx >= len(qids):
        return redirect(url_for("test.scenario_preview"))

    return redirect(url_for("test.scenario_question", idx=next_idx))


# ======================================
# Scenario preview
# ======================================
@test_bp.get("/scenario/preview")
@login_required
def scenario_preview():
    lang = session.get("lang", "EN").upper()
    qids = session.get("scenario_qids") or []
    answers = session.get("scenario_answers") or {}

    if not qids:
        return redirect(url_for("test.scenario_start"))

    qs_all = {int(q["questionID"]): dict(q) for q in list_scenario_questions(lang=lang)}

    snapshot = []
    for qid in qids:
        qid = int(qid)
        q = qs_all.get(qid)
        if not q:
            continue

        opts = [dict(o) for o in list_options_for_question(qid, lang)]
        for o in opts:
            o["optionID"] = int(o["optionID"])
            o["questionID"] = int(o.get("questionID", qid))
            o["optionText"] = (o.get("optionText") or "").strip()
            o["optionKey"] = (o.get("optionKey") or "").strip().upper()
            o["EIScore"] = int(o.get("EIScore", 0))
            o["SNScore"] = int(o.get("SNScore", 0))
            o["TFScore"] = int(o.get("TFScore", 0))
            o["JPScore"] = int(o.get("JPScore", 0))

        snapshot.append({
            "questionID": qid,
            "groupID": int(q.get("groupID") or qid),
            "scenarioText": q.get("scenarioText", ""),
            "category": q.get("categoryName") or q.get("category") or "",
            "options": opts
        })

    if len(answers) < len(snapshot):
        flash(t_py("scenario_need_complete"), "warning")
        for i, q in enumerate(snapshot):
            if str(q["questionID"]) not in answers:
                return redirect(url_for("test.scenario_question", idx=i))
        return redirect(url_for("test.scenario_question", idx=0))

    preview_items = []

    for idx, q in enumerate(snapshot):
        qid = int(q["questionID"])
        oid = answers.get(str(qid))
        if oid is None:
            continue

        oid = int(oid)
        opt_text = ""
        letter = "?"

        for j, o in enumerate(q["options"]):
            if int(o["optionID"]) == oid:
                opt_text = o["optionText"]
                letter = ["A", "B", "C", "D"][j] if 0 <= j <= 3 else "?"
                break

        preview_items.append({
            "num": idx + 1,
            "questionID": qid,
            "questionText": q.get("scenarioText", ""),
            "answerText": f"{letter} - {opt_text}",
            "editUrl": url_for("test.scenario_question", idx=idx, return_to_review=1)
        })

    user_id = session["user_id"]
    profile_context = build_profile_context_for_prediction(user_id)

    top3, raw_payload = predict_top3_from_snapshot(
        snapshot,
        answers,
        profile_context=profile_context
    )

    store_pending_prediction(
        top3,
        raw_payload=raw_payload,
        profile_context=profile_context
    )

    return render_template("scenario_preview.html", items=preview_items)


# ======================================
# Scenario confirm
# ======================================
@test_bp.post("/scenario/confirm")
@login_required
def scenario_confirm():
    return redirect(url_for("result.result_page"))
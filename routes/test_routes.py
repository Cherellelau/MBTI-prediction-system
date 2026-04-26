from functools import wraps
import time

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
    list_scenario_questions_with_options,
)
from i18n import TRANSLATIONS
from services.prediction_service import (
    ml_predict_top3_with_profile,
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
# Scenario cache helpers
# ======================================
def get_scenario_bank(lang: str):
    """
    Cache all scenario questions+options by language in server memory.
    This avoids repeated DB queries and does NOT bloat Flask session cookies.
    """
    lang = (lang or "EN").upper()
    raw_qs = list_scenario_questions_with_options(lang=lang)

    cleaned = []
    for q in raw_qs:
        item = dict(q)
        qid = int(item["questionID"])

        cleaned_options = []
        for o in item.get("options", []):
            od = dict(o)
            cleaned_options.append({
                "optionID": int(od["optionID"]),
                "questionID": int(od.get("questionID", qid)),
                "optionText": (od.get("optionText") or "").strip(),
                "optionKey": (od.get("optionKey") or "").strip().upper(),
                "EIScore": int(od.get("EIScore", 0) or 0),
                "SNScore": int(od.get("SNScore", 0) or 0),
                "TFScore": int(od.get("TFScore", 0) or 0),
                "JPScore": int(od.get("JPScore", 0) or 0),
            })

        cleaned.append({
            "questionID": qid,
            "groupID": int(item.get("groupID") or qid),
            "scenarioText": item.get("scenarioText", ""),
            "category": item.get("categoryName") or item.get("category") or "",
            "options": cleaned_options,
        })

    return cleaned


def get_scenario_by_qid(lang: str, qid: int):
    bank = get_scenario_bank(lang)
    return next((q for q in bank if int(q["questionID"]) == int(qid)), None)


def get_snapshot_from_qids(lang: str, qids):
    qid_set = {int(x) for x in qids}
    bank = get_scenario_bank(lang)
    return [q for q in bank if int(q["questionID"]) in qid_set]


def predict_top3_from_snapshot(snapshot, answers, profile_context=None):
    print("[DEBUG] predict_top3_from_snapshot start", flush=True)

    ei = sn = tf = jp = 0
    raw_answers = []

    for q in (snapshot or []):
        qid = int(q.get("questionID", 0))
        if not qid:
            continue

        gid = int(q.get("groupID") or qid)

        saved = answers.get(str(qid))
        if not saved:
            continue

        oid = saved.get("optionID")
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

    print("[DEBUG] finished score accumulation", flush=True)

    profile_scores = score_profile_mbti(profile_context)
    print(f"[DEBUG] profile_scores: {profile_scores}", flush=True)

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
    print(f"[DEBUG] combined_scores: {combined_scores}", flush=True)

    ei = combined_scores["EI"]
    sn = combined_scores["SN"]
    tf = combined_scores["TF"]
    jp = combined_scores["JP"]

    t1 = scores_to_mbti(ei, sn, tf, jp)
    c1 = confidence_from_scores(ei, sn, tf, jp)
    print(f"[DEBUG] t1={t1}, c1={c1}", flush=True)

    # generate 2 alternative types by flipping different positions
    def flip_at(code, pos):
        pairs = {
            0: {"E": "I", "I": "E"},
            1: {"S": "N", "N": "S"},
            2: {"T": "F", "F": "T"},
            3: {"J": "P", "P": "J"},
        }
        ch = code[pos]
        new_ch = pairs[pos].get(ch, ch)
        return code[:pos] + new_ch + code[pos + 1:]

    candidates = [
        t1,
        flip_at(t1, 0),
        flip_at(t1, 1),
        flip_at(t1, 2),
        flip_at(t1, 3),
    ]

    uniq = []
    for t in candidates:
        if t not in uniq:
            uniq.append(t)
        if len(uniq) == 3:
            break

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

    print("[DEBUG] predict_top3_from_snapshot end", flush=True)
    return top3, raw_payload


# ======================================
# Normal text test
# ======================================
@test_bp.get("/test")
@login_required
def test():
    if not user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.profile_manual"))

    return render_template("test.html")


@test_bp.post("/submit")
@login_required
def submit():
    raw_text = request.form.get("raw_text", "").strip()
    if not raw_text:
        flash(t_py("msg_enter_text"), "error")
        return redirect(url_for("test.test"))

    user_id = session["user_id"]
    profile_context = build_profile_context_for_prediction(user_id)

    top3 = ml_predict_top3_with_profile(
        raw_text,
        profile_context=profile_context
    )

    store_pending_prediction(
        top3,
        raw_text=raw_text,
        profile_context=profile_context
    )

    return redirect(url_for("result.result_page"))


# ======================================
# Scenario start
# ======================================
@test_bp.get("/scenario")
@login_required
def scenario_start():
    lang = session.get("lang", "EN").upper()

    for k in [
        "scenario_qids",
        "scenario_answers",
        "scenario_idx",
        "scenario_snapshot_lang",
    ]:
        session.pop(k, None)

    try:
        get_scenario_bank.cache_clear()
    except Exception:
        pass

    qs = get_scenario_bank(lang)
    if not qs:
        flash("No scenario questions found in DB.", "error")
        return redirect(url_for("test.test"))

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
    item = get_scenario_by_qid(lang, qid)

    if not item:
        return redirect(url_for("test.scenario_start"))

    options = item.get("options", [])
    selected_saved = (session.get("scenario_answers") or {}).get(str(qid))
    selected = None

    if isinstance(selected_saved, dict):
        selected = selected_saved.get("optionID")
    else:
        selected = selected_saved

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

    try:
        qid_int = int(qid)
        oid_int = int(oid)
    except Exception:
        flash(t_py("scenario_choose_one"), "error")
        return redirect(url_for("test.scenario_question", idx=idx))

    lang = session.get("lang", "EN").upper()
    q = get_scenario_by_qid(lang, qid_int)
    options = q.get("options", []) if q else []

    chosen_opt = None
    chosen_idx = -1
    for i, o in enumerate(options):
        try:
            if int(o.get("optionID", 0)) == oid_int:
                chosen_opt = o
                chosen_idx = i
                break
        except Exception:
            continue

    if not chosen_opt:
        flash(t_py("scenario_choose_one"), "error")
        return redirect(url_for("test.scenario_question", idx=idx))

    option_key = (chosen_opt.get("optionKey") or "").strip().upper()
    if option_key not in ("A", "B", "C", "D"):
        option_key = option_letter_from_index(chosen_idx)

    answers = session.get("scenario_answers") or {}
    answers[str(qid_int)] = {
        "optionID": oid_int,
        "optionKey": option_key,
        "EIScore": int(chosen_opt.get("EIScore", 0) or 0),
        "SNScore": int(chosen_opt.get("SNScore", 0) or 0),
        "TFScore": int(chosen_opt.get("TFScore", 0) or 0),
        "JPScore": int(chosen_opt.get("JPScore", 0) or 0),
    }

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

    qmap = {int(q["questionID"]): q for q in get_scenario_bank(lang)}
    preview_items = []

    for idx, qid in enumerate(qids):
        qid = int(qid)
        q = qmap.get(qid)
        if not q:
            continue

        saved = answers.get(str(qid))
        if not saved:
            flash(t_py("scenario_need_complete"), "warning")
            return redirect(url_for("test.scenario_question", idx=idx))

        chosen_oid = int(saved.get("optionID", 0))
        letter = saved.get("optionKey", "?")
        opt_text = ""

        for o in q.get("options", []):
            if int(o["optionID"]) == chosen_oid:
                opt_text = o["optionText"]
                break

        preview_items.append({
            "num": idx + 1,
            "questionID": qid,
            "questionText": q.get("scenarioText", ""),
            "answerText": f"{letter} - {opt_text}",
            "editUrl": url_for("test.scenario_question", idx=idx, return_to_review=1)
        })

    return render_template("scenario_preview.html", items=preview_items)


# ======================================
# Scenario confirm
# ======================================
@test_bp.post("/scenario/confirm")
@login_required
def scenario_confirm():
    t0 = time.perf_counter()

    lang = session.get("lang", "EN").upper()
    qids = session.get("scenario_qids") or []
    answers = session.get("scenario_answers") or {}

    if not qids:
        return redirect(url_for("test.scenario_start"))

    if len(answers) < len(qids):
        flash(t_py("scenario_need_complete"), "warning")
        return redirect(url_for("test.scenario_preview"))

    t1 = time.perf_counter()
    snapshot = get_snapshot_from_qids(lang, qids)
    print(f"[TIMING] snapshot: {time.perf_counter() - t1:.4f}s", flush=True)

    user_id = session["user_id"]

    t2 = time.perf_counter()
    profile_context = build_profile_context_for_prediction(user_id)
    print(f"[TIMING] profile_context: {time.perf_counter() - t2:.4f}s", flush=True)

    print("[TIMING] before predict_top3_from_snapshot", flush=True)
    t3 = time.perf_counter()
    top3, raw_payload = predict_top3_from_snapshot(
        snapshot=snapshot,
        answers=answers,
        profile_context=profile_context
    )
    print(f"[TIMING] predict_top3: {time.perf_counter() - t3:.4f}s", flush=True)

    print("[TIMING] before store_pending_prediction", flush=True)
    t4 = time.perf_counter()
    store_pending_prediction(
        top3,
        raw_payload=raw_payload,
        profile_context=profile_context
    )
    print(f"[TIMING] store_pending_prediction: {time.perf_counter() - t4:.4f}s", flush=True)

    print(f"[TIMING] scenario_confirm total: {time.perf_counter() - t0:.4f}s", flush=True)

    return redirect(url_for("result.result_page"))

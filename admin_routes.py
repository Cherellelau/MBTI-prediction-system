from functools import wraps
import os
import requests

import db
from flask import Blueprint, session, redirect, url_for, abort, request, render_template, flash, jsonify
from auth import hash_password
from db import upsert_scenario_question, next_question_group_id

admin_bp = Blueprint("admin", __name__)
VALID_CATEGORIES = {"EI", "SN", "TF", "JP"}

def clamp_int(v, lo=-5, hi=5):
    try:
        n = int(v)
    except Exception:
        n = 0
    if n < lo:
        n = lo
    if n > hi:
        n = hi
    return n

def safe_int(v, default=1):
    try:
        return int(v)
    except Exception:
        return default
    
def clear_scenario_cache():
    for k in ["scenario_snapshot", "scenario_qids", "scenario_gids",
              "scenario_answers", "scenario_idx", "scenario_snapshot_lang"]:
        session.pop(k, None)

    session.modified = True

# -----------------------------
# Auth / Guard
# -----------------------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("auth.login"))
        user = db.get_user_by_id(uid)
        if not user or int(user.get("isAdmin", 0)) != 1:
            abort(403)
        return f(*args, **kwargs)
    return wrapper

# -----------------------------
# Scenario routes
# -----------------------------
@admin_bp.route("/admin/scenario")
@admin_required
def scenario_list():
    questions = db.list_scenario_questions("EN")
    return render_template("admin/admin_scenario_list.html", questions=questions, lang="EN")

@admin_bp.route("/admin/scenario/new", methods=["GET", "POST"])
@admin_required
def scenario_new():
    if request.method == "POST":
        category = (request.form.get("category") or "EI").strip().upper()
        
        if category not in VALID_CATEGORIES:
            flash("Invalid category.", "error")
            return redirect(url_for("admin.scenario_new"))

        text_en = (request.form.get("scenarioText_en") or "").strip()
        text_bm = (request.form.get("scenarioText_bm") or "").strip()
        text_zh = (request.form.get("scenarioText_zh") or "").strip()

        if not text_en:
            flash("English scenario question is required.", "error")
            return redirect(url_for("admin.scenario_new"))

        gid = next_question_group_id()

        upsert_scenario_question(gid, "EN", category, text_en)
        upsert_scenario_question(gid, "BM", category, text_bm or text_en)
        upsert_scenario_question(gid, "ZH", category, text_zh or text_en)

        # fetch EN/BM/ZH question rows
        q_en = db.admin_get_question_by_group_lang(gid, "EN")
        q_bm = db.admin_get_question_by_group_lang(gid, "BM")
        q_zh = db.admin_get_question_by_group_lang(gid, "ZH")

        qid_en = int(q_en["questionID"])
        qid_bm = int(q_bm["questionID"])
        qid_zh = int(q_zh["questionID"])

        # create default options first (A-D)
        db.ensure_default_options(qid_en)
        db.ensure_default_options(qid_bm)
        db.ensure_default_options(qid_zh)

        # ✅ NOW: write the submitted option texts + scores into the EN options
        # and mirror into BM/ZH (you can keep BM/ZH as EN for now)
        keys = ["A", "B", "C", "D"]
        for k in keys:
            opt_en = (request.form.get(f"optText_{k}") or "").strip()

            # your create page currently has NO name for opt BM/ZH textareas,
            # so these will be empty unless you add name="".
            opt_bm = (request.form.get(f"optText_bm_{k}") or "").strip()
            opt_zh = (request.form.get(f"optText_zh_{k}") or "").strip()

            ei = clamp_int(request.form.get(f"optEI_{k}", 0))
            sn = clamp_int(request.form.get(f"optSN_{k}", 0))
            tf = clamp_int(request.form.get(f"optTF_{k}", 0))
            jp = clamp_int(request.form.get(f"optJP_{k}", 0))

            if not opt_en:
                flash(f"Option {k} text is required.", "error")
                return redirect(url_for("admin.scenario_new"))

            # update by (question_id + option_key)
            db.admin_update_option_by_question_key_full(qid_en, k, opt_en, ei, sn, tf, jp)
            db.admin_update_option_by_question_key_full(qid_bm, k, opt_bm or opt_en, ei, sn, tf, jp)
            db.admin_update_option_by_question_key_full(qid_zh, k, opt_zh or opt_en, ei, sn, tf, jp)

        clear_scenario_cache()
        flash("Question + options created (EN/BM/ZH).", "success")
        return redirect(url_for("admin.scenario_edit", qid=qid_en))

    return render_template("admin/admin_scenario_new.html", lang="EN")

@admin_bp.route("/admin/scenario/<int:qid>/edit")
@admin_required
def scenario_edit(qid):
    q = db.admin_get_question(qid)
    if not q:
        flash("Question not found.", "error")
        return redirect(url_for("admin.scenario_list"))

    gid = int(q.get("groupID") or qid)

    # ✅ EN options
    opts = db.admin_get_options(int(q["questionID"]))

    # ✅ load BM/ZH question rows for scenario textareas
    q_bm = db.admin_get_question_by_group_lang(gid, "BM")
    q_zh = db.admin_get_question_by_group_lang(gid, "ZH")

    # ✅ get BM/ZH questionIDs
    qids = db.get_question_ids_by_group(gid)
    qid_bm = qids.get("BM")
    qid_zh = qids.get("ZH")

    # ✅ BM/ZH options
    opts_bm = db.admin_get_options(int(qid_bm)) if qid_bm else []
    opts_zh = db.admin_get_options(int(qid_zh)) if qid_zh else []

    bm_map = {x["optionKey"]: x["optionText"] for x in (opts_bm or [])}
    zh_map = {x["optionKey"]: x["optionText"] for x in (opts_zh or [])}

    for o in opts:
        k = o["optionKey"]
        o["optionTextBM"] = bm_map.get(k, "")
        o["optionTextZH"] = zh_map.get(k, "")

    return render_template(
        "admin/admin_scenario_edit.html",  # adjust if your template path differs
        q=q,
        q_bm=q_bm,
        q_zh=q_zh,
        opts=opts
    )

# NEW: Save Question + All Options (A–D) in ONE submit
@admin_bp.route("/admin/scenario/<int:qid>/edit/save-all", methods=["POST"])
@admin_required
def scenario_edit_save_all(qid):
    q = db.admin_get_question(qid)
    if not q:
        flash("Question not found.", "error")
        return redirect(url_for("admin.scenario_list"))

    gid = int(q.get("groupID") or qid)
    category = (request.form.get("category") or "EI").strip().upper()

    # Read 3 language fields
    text_en = (request.form.get("scenarioText_en") or "").strip()
    text_bm = (request.form.get("scenarioText_bm") or "").strip()
    text_zh = (request.form.get("scenarioText_zh") or "").strip()

    if not text_en:
        flash("English scenario question is required.", "error")
        return redirect(url_for("admin.scenario_edit", qid=qid))

    # ✅ Update EN always
    upsert_scenario_question(gid, "EN", category, text_en)

    # ✅ Update BM/ZH only if provided (otherwise keep existing)
    if text_bm:
        upsert_scenario_question(gid, "BM", category, text_bm)
    if text_zh:
        upsert_scenario_question(gid, "ZH", category, text_zh)

    # ✅ Get BM/ZH questionIDs
    qids = db.get_question_ids_by_group(gid)
    qid_bm = qids.get("BM")
    qid_zh = qids.get("ZH")

    if qid_bm:
        db.ensure_default_options(int(qid_bm))
    if qid_zh:
        db.ensure_default_options(int(qid_zh))

    # ✅ Update 4 options
    keys = ["A", "B", "C", "D"]
    for k in keys:
        option_id = request.form.get(f"optionID_{k}")

        # EN required
        option_text_en = (request.form.get(f"optionText_{k}") or "").strip()

        # BM/ZH optional 
        option_text_bm = (request.form.get(f"optionTextBM_{k}") or "").strip()
        option_text_zh = (request.form.get(f"optionTextZH_{k}") or "").strip()

        if not option_id:
            flash(f"Missing option ID for {k}.", "error")
            return redirect(url_for("admin.scenario_edit", qid=qid))

        if not option_text_en:
            flash(f"Option {k} text is required.", "error")
            return redirect(url_for("admin.scenario_edit", qid=qid))

        ei = clamp_int(request.form.get(f"EIScore_{k}", 0))
        sn = clamp_int(request.form.get(f"SNScore_{k}", 0))
        tf = clamp_int(request.form.get(f"TFScore_{k}", 0))
        jp = clamp_int(request.form.get(f"JPScore_{k}", 0))

        # ✅ Update EN option
        db.admin_update_option(int(option_id), k, option_text_en, ei, sn, tf, jp)

        # ✅ Update BM/ZH options only if text provided (don't overwrite with EN)
        if qid_bm and option_text_bm:
            db.admin_update_option_by_question_key_full(int(qid_bm), k, option_text_bm, ei, sn, tf, jp)

        if qid_zh and option_text_zh:
            db.admin_update_option_by_question_key_full(int(qid_zh), k, option_text_zh, ei, sn, tf, jp)

    clear_scenario_cache()
    flash("Question + options updated (EN/BM/ZH).", "success")
    return redirect(url_for("admin.scenario_edit", qid=qid))

@admin_bp.route("/admin/option/<int:option_id>/edit", methods=["POST"])
@admin_required
def option_edit(option_id):
    optionKey = request.form.get("optionKey", "A")
    optionText = (request.form.get("optionText", "") or "").strip()

    ei = clamp_int(request.form.get("EIScore", 0))
    sn = clamp_int(request.form.get("SNScore", 0))
    tf = clamp_int(request.form.get("TFScore", 0))
    jp = clamp_int(request.form.get("JPScore", 0))

    qid = int(request.form.get("questionID"))

    db.admin_update_option(option_id, optionKey, optionText, ei, sn, tf, jp)
    flash("Option updated.")
    return redirect(url_for("admin.scenario_edit", qid=qid))


@admin_bp.route("/admin/option/<int:option_id>/delete", methods=["POST"])
@admin_required
def option_delete(option_id):
    qid = int(request.form.get("questionID"))
    flash("Deleting options is disabled because each scenario must keep 4 options.", "error")
    return redirect(url_for("admin.scenario_edit", qid=qid))


@admin_bp.route("/admin/scenario/<int:qid>/delete", methods=["POST"])
@admin_required
def scenario_delete(qid):
    q = db.admin_get_question(qid)
    if not q:
        flash("Question not found.", "error")
        return redirect(url_for("admin.scenario_list"))

    # ✅ This handles BOTH:
    # - correct groupID deletion
    # - old seeded BM/ZH not linked properly (slot fallback)
    db.admin_delete_question(qid)

    clear_scenario_cache()
    flash("Question deleted (EN/BM/ZH).", "success")
    return redirect(url_for("admin.scenario_list"))

# -----------------------------
# Career routes
# -----------------------------
VALID_TYPES = [a + b + c + d for a in "IE" for b in "NS" for c in "TF" for d in "JP"]


@admin_bp.route("/admin/careers")
@admin_required
def careers_list():
    type_code = (request.args.get("type") or "").upper().strip()
    if type_code and type_code not in VALID_TYPES:
        type_code = ""

    rows = db.admin_list_careers(type_code or None)
    return render_template(
        "admin/admin_careers_list.html",
        rows=rows,
        type_code=type_code,
        types=VALID_TYPES
    )

def safe_int(v, default=1):
    try:
        return int(v)
    except Exception:
        return default

@admin_bp.route("/admin/careers/create", methods=["POST"])
@admin_required
def careers_create():
    type_code = (request.form.get("typeCode") or "").upper().strip()
    career_key = (request.form.get("careerKey") or "").strip().lower()
    url_ = (request.form.get("url") or "").strip()

    # you don't have sortOrder input in HTML, so default safely
    sort_order = safe_int(request.form.get("sortOrder"), 1)

    # NEW: titles
    title_en = (request.form.get("title_en") or "").strip()
    title_bm = (request.form.get("title_bm") or "").strip()
    title_zh = (request.form.get("title_zh") or "").strip()

    # descriptions
    desc_en = (request.form.get("desc_en") or "").strip()
    desc_bm = (request.form.get("desc_bm") or "").strip()
    desc_zh = (request.form.get("desc_zh") or "").strip()

    if type_code not in VALID_TYPES:
        flash("Invalid MBTI type.", "error")
        return redirect(url_for("admin.careers_list"))

    # ✅ EN required
    if not title_en or not desc_en:
        flash("English career name (title) and description are required.", "error")
        return redirect(url_for("admin.careers_list", type=type_code))

    try:
        # ✅ if you changed db.admin_create_career to UPSERT, this won't error on duplicates
        new_id = db.admin_create_career(type_code, career_key, url_, sort_order)

        # ✅ save Career_Text (title + desc)
        db.admin_upsert_career_text(career_key, "EN", title_en, desc_en)
        db.admin_upsert_career_text(career_key, "BM", title_bm, desc_bm)
        db.admin_upsert_career_text(career_key, "ZH", title_zh, desc_zh)

        flash("Career added.", "success")
        return redirect(url_for("admin.careers_edit", career_id=new_id))

    except Exception as e:
        flash(f"Create failed: {e}", "error")
        return redirect(url_for("admin.careers_list", type=type_code))

@admin_bp.route("/admin/careers/<int:career_id>/edit")
@admin_required
def careers_edit(career_id):
    career = db.admin_get_career(career_id)
    if not career:
        flash("Career not found.", "error")
        return redirect(url_for("admin.careers_list"))

    texts = db.admin_get_career_text(career["careerKey"])
    return render_template("admin/admin_careers_edit.html", career=career, texts=texts)

@admin_bp.route("/admin/careers/<int:career_id>/update", methods=["POST"])
@admin_required
def careers_update(career_id):
    career = db.admin_get_career(career_id)
    if not career:
        flash("Career not found.", "error")
        return redirect(url_for("admin.careers_list"))

    career_key = (request.form.get("careerKey") or "").strip().lower()
    url_ = (request.form.get("url") or "").strip()
    sort_order = safe_int(request.form.get("sortOrder"), 1)

    # ✅ NEW: titles
    title_en = (request.form.get("title_en") or "").strip()
    title_bm = (request.form.get("title_bm") or "").strip()
    title_zh = (request.form.get("title_zh") or "").strip()

    # descriptions
    desc_en = (request.form.get("desc_en") or "").strip()
    desc_bm = (request.form.get("desc_bm") or "").strip()
    desc_zh = (request.form.get("desc_zh") or "").strip()

    if not title_en or not desc_en:
        flash("English career name (title) and description are required.", "error")
        return redirect(url_for("admin.careers_edit", career_id=career_id))

    db.admin_update_career(career_id, career_key, url_, sort_order)

    # ✅ save Career_Text (title + desc)
    db.admin_upsert_career_text(career_key, "EN", title_en, desc_en)
    db.admin_upsert_career_text(career_key, "BM", title_bm, desc_bm)
    db.admin_upsert_career_text(career_key, "ZH", title_zh, desc_zh)

    flash("Career updated.", "success")
    return redirect(url_for("admin.careers_list", type=career["typeCode"]))

@admin_bp.route("/admin/careers/<int:career_id>/delete", methods=["POST"])
@admin_required
def careers_delete(career_id):
    career = db.admin_get_career(career_id)
    if not career:
        flash("Career not found.", "error")
        return redirect(url_for("admin.careers_list"))

    try:
        db.admin_delete_career(career_id)
        flash("Career deleted.", "success")
    except Exception as e:
        flash(f"Delete failed: {e}", "error")

    return redirect(url_for("admin.careers_list", type=career["typeCode"]))

# -----------------------------
# User Management (Admin)
# - view all users
# - view any user's timeline/records
# - reset user password
# -----------------------------

@admin_bp.route("/admin/users")
@admin_required
def admin_users_list():
    q = (request.args.get("q") or "").strip().lower()
    users = db.admin_list_users(q=q)
    return render_template("admin/admin_users_list.html", users=users, q=q)


@admin_bp.route("/admin/users/<int:uid>/records")
@admin_required
def admin_user_records(uid):
    """
    Admin view: show a specific user's timeline using your existing timeline.html
    We reuse the same chart logic in app.py but inside admin blueprint.
    """
    user = db.get_user_by_id(uid)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin.admin_users_list"))

    preset = request.args.get("preset", "all")
    start = request.args.get("start")
    end = request.args.get("end")
    q = (request.args.get("q") or "").strip().upper()

    # for admin view, allow filters too (optional)
    from datetime import datetime, timedelta

    today = datetime.now().date()
    if preset in ("7d", "30d", "12m") and (not start and not end):
        if preset == "7d":
            start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        elif preset == "30d":
            start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        elif preset == "12m":
            start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

    # DB fetch
    if start or end:
        results_raw = db.list_results_for_user_filtered(uid, start, end)
    else:
        results_raw = db.list_results_for_user(uid)

    results = [dict(r) for r in results_raw]

    # Optional search filter
    if q:
        results = [r for r in results if (r.get("typeCode") or "").upper().startswith(q)]

    # --- chart_data (same logic as your app.py) ---
    def parse_dt(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", ""))
        except Exception:
            try:
                return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

    results_sorted = sorted(results, key=lambda r: parse_dt(r.get("createdAt")) or datetime.min)

    labels, ei, sn, tf, jp = [], [], [], [], []
    for r in results_sorted:
        code = (r.get("typeCode") or "").upper()
        dt = parse_dt(r.get("createdAt"))
        if len(code) != 4 or not dt:
            continue
        labels.append(dt.strftime("%b %Y"))
        ei.append(1 if code[0] == "E" else 0)
        sn.append(1 if code[1] == "S" else 0)
        tf.append(1 if code[2] == "T" else 0)
        jp.append(1 if code[3] == "J" else 0)

    chart_data = {"labels": labels, "ei": ei, "sn": sn, "tf": tf, "jp": jp}

    total = len(results)
    latest = results_sorted[-1] if results_sorted else None
    summary = {
        "total": total,
        "latest_type": latest["typeCode"] if latest else None,
        "latest_date": latest["createdAt"] if latest else None,
        "preset": preset,
        "start": start or "",
        "end": end or "",
        "q": q or ""
    }

    # IMPORTANT: view_only=False so admin still sees filters if you want
    return render_template(
        "timeline.html",
        results=results,
        summary=summary,
        chart_data=chart_data,
        highlight=None,
        view_only=False,

        # extra info for admin header (optional)
        admin_view=True,
        target_user=user
    )


@admin_bp.route("/admin/users/<int:uid>/password", methods=["GET", "POST"])
@admin_required
def admin_reset_user_password(uid):
    user = db.get_user_by_id(uid)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin.admin_users_list"))

    if request.method == "POST":
        new_pw = (request.form.get("new_password") or "").strip()
        confirm_pw = (request.form.get("confirm_password") or "").strip()

        if not new_pw or len(new_pw) < 6 or len(new_pw) > 8:
            flash("Password must be 6–8 characters.", "error")
            return redirect(url_for("admin.admin_reset_user_password", uid=uid))

        if new_pw != confirm_pw:
            flash("Passwords do not match.", "error")
            return redirect(url_for("admin.admin_reset_user_password", uid=uid))

        try:
            db.admin_set_user_password(uid, hash_password(new_pw))
            flash("✅ Password updated successfully.", "success")
            return redirect(url_for("admin.admin_users_list"))
        except Exception as e:
            flash(f"Failed to update password: {e}", "error")
            return redirect(url_for("admin.admin_reset_user_password", uid=uid))

    return render_template("admin/admin_user_reset_password.html", u=user)


# -----------------------------
# Auto-Translate (Admin) - DeepL (Header-based Auth)
# -----------------------------
DEEPL_API_KEY = (os.environ.get("DEEPL_API_KEY", "") or "").strip()
DEEPL_ENDPOINT = (os.environ.get("DEEPL_ENDPOINT", "") or "").strip() or "https://api-free.deepl.com/v2/translate"
# Paid plan endpoint: "https://api.deepl.com/v2/translate"


def _deepl_target(target: str) -> str:
    """
    Our UI targets: BM or ZH
    DeepL expects: MS (Malay) or ZH (Chinese)
    """
    t = (target or "").upper().strip()
    if t == "BM":
        return "MS"
    if t == "ZH":
        return "ZH"
    raise ValueError("target must be BM or ZH")


def deepl_translate(text: str, target_lang: str) -> str:
    if not DEEPL_API_KEY:
        raise RuntimeError("DEEPL_API_KEY is not set")

    # ✅ New DeepL auth: header-based
    headers = {
        "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}",
    }

    resp = requests.post(
        DEEPL_ENDPOINT,
        headers=headers,
        data={
            "text": text,
            "target_lang": target_lang
        },
        timeout=20
    )

    # Better error message
    if resp.status_code >= 400:
        try:
            j = resp.json()
        except Exception:
            j = {"message": resp.text}
        raise RuntimeError(f"DeepL error {resp.status_code}: {j}")

    data = resp.json()
    return (data["translations"][0]["text"] or "").strip()


@admin_bp.post("/admin/translate")
@admin_required
def admin_translate():
    """
    Accepts:
      { "text": "...", "target": "BM"|"ZH" }
    Returns:
      { "translated": "..." }
    """
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    target = (payload.get("target") or "").strip().upper()

    if not text:
        return jsonify({"error": "text required"}), 400
    if target not in ("BM", "ZH"):
        return jsonify({"error": "target must be BM or ZH"}), 400

    try:
        translated = deepl_translate(text, _deepl_target(target))
        return jsonify({"translated": translated}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.post("/admin/translate/bulk")
@admin_required
def admin_translate_bulk():
    """
    Accepts EITHER:
      A) { "text": "...", "targets": ["BM","ZH"] }
      B) { "items": [ { "id":"q", "text":"...", "targets":["BM","ZH"] }, ... ] }

    Returns:
      A) { "translations": { "BM":"...", "ZH":"..." } }
      B) { "items": [ { "id":"q", "translations":{...} }, ... ] }
    """
    payload = request.get_json(silent=True) or {}

    # --- Mode B: items ---
    if isinstance(payload.get("items"), list):
        out_items = []
        for item in payload["items"]:
            _id = item.get("id")
            txt = (item.get("text") or "").strip()
            targets = item.get("targets") or ["BM", "ZH"]

            if not txt:
                out_items.append({"id": _id, "error": "text required", "translations": {}})
                continue

            translations = {}
            try:
                for t in targets:
                    t2 = (t or "").upper().strip()
                    if t2 not in ("BM", "ZH"):
                        continue
                    translations[t2] = deepl_translate(txt, _deepl_target(t2))
                out_items.append({"id": _id, "translations": translations})
            except Exception as e:
                out_items.append({"id": _id, "error": str(e), "translations": translations})

        return jsonify({"items": out_items}), 200

    # --- Mode A: single text + targets ---
    text = (payload.get("text") or "").strip()
    targets = payload.get("targets") or ["BM", "ZH"]

    if not text:
        return jsonify({"error": "Invalid payload. Use {text, targets} or {items}."}), 400

    translations = {}
    try:
        for t in targets:
            t2 = (t or "").upper().strip()
            if t2 not in ("BM", "ZH"):
                continue
            translations[t2] = deepl_translate(text, _deepl_target(t2))
        return jsonify({"translations": translations}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.post("/admin/scenario/<int:qid>/translate/save")
@admin_required
def scenario_translate_save(qid):
    q = db.admin_get_question(qid)
    if not q:
        return jsonify({"error": "Question not found"}), 404

    payload = request.get_json(silent=True) or {}   # ✅ safe

    group_id = int(q.get("groupID") or qid)
    category = (payload.get("category") or q.get("category") or "EI").strip().upper()
    
    if category not in VALID_CATEGORIES:
        return jsonify({"error": "Invalid category"}), 400

    scenario_bm = (payload.get("scenarioBm") or "").strip()
    scenario_zh = (payload.get("scenarioZh") or "").strip()

    out = {"BM": None, "ZH": None}

    if scenario_bm:
        bm_qid = db.admin_upsert_question_translation(group_id, "BM", category, scenario_bm)
        db.ensure_default_options(bm_qid)
        out["BM"] = bm_qid

    if scenario_zh:
        zh_qid = db.admin_upsert_question_translation(group_id, "ZH", category, scenario_zh)
        db.ensure_default_options(zh_qid)
        out["ZH"] = zh_qid

    return jsonify({"ok": True, "created": out}), 200

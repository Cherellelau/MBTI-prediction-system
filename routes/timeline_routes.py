from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)

from db import (
    list_results_for_user,
    list_results_for_user_filtered,
)
from i18n import TRANSLATIONS
from services.email_service import send_timeline_summary_email

timeline_bp = Blueprint("timeline", __name__)


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
            flash(t_py("msg_login_required"), "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", ""))
    except Exception:
        try:
            return datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

def parse_conf(r):
    try:
        return float(r.get("confidenceScore", 0) or 0)
    except Exception:
        return 0.0

def sort_timeline_results(results, sort_by: str):
    if sort_by == "oldest":
        return sorted(results, key=lambda r: parse_dt(r.get("createdAt")) or datetime.min)
    if sort_by == "type_asc":
        return sorted(results, key=lambda r: (r.get("typeCode") or ""))
    if sort_by == "type_desc":
        return sorted(results, key=lambda r: (r.get("typeCode") or ""), reverse=True)
    if sort_by == "conf_desc":
        return sorted(results, key=parse_conf, reverse=True)
    if sort_by == "conf_asc":
        return sorted(results, key=parse_conf)

    return sorted(
        results,
        key=lambda r: parse_dt(r.get("createdAt")) or datetime.min,
        reverse=True
    )

def is_fetch_request():
    return request.headers.get("X-Requested-With") == "fetch"

def email_error_response(msg: str, status_code: int, preset: str, start: str, end: str, q: str, sort_by: str, category: str = "error"):
    if is_fetch_request():
        return jsonify({"ok": False, "msg": msg}), status_code

    flash(msg, category)
    return timeline_redirect(preset, start, end, q, sort_by)

# ======================================
# Timeline data helpers
# ======================================
def get_timeline_results(user_id: int, start: str = "", end: str = "", q: str = ""):
    if start or end:
        results_raw = list_results_for_user_filtered(user_id, start, end)
    else:
        results_raw = list_results_for_user(user_id)

    results = [dict(r) for r in results_raw]

    for r in results:
        code = (r.get("typeCode") or "").upper()
        r["eiSide"] = code[0] if len(code) >= 1 else "-"
        r["snSide"] = code[1] if len(code) >= 2 else "-"
        r["tfSide"] = code[2] if len(code) >= 3 else "-"
        r["jpSide"] = code[3] if len(code) >= 4 else "-"

    if q:
        q = q.strip().upper()
        results = [r for r in results if (r.get("typeCode") or "").upper().startswith(q)]

    return results


def apply_timeline_preset(preset: str, start: str = "", end: str = ""):
    today = datetime.now().date()

    if preset in ("7d", "30d", "12m") and (not start and not end):
        if preset == "7d":
            start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        elif preset == "30d":
            start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        elif preset == "12m":
            start = (today - timedelta(days=365)).strftime("%Y-%m-%d")

        end = today.strftime("%Y-%m-%d")

    return start, end

def timeline_redirect(preset: str, start: str, end: str, q: str, sort_by: str):
    return redirect(url_for(
        "timeline.timeline",
        preset=preset,
        start=start,
        end=end,
        q=q,
        sort_by=sort_by
    ))

# ======================================
# Timeline page
# ======================================
@timeline_bp.get("/timeline")
@login_required
def timeline():
    preset = request.args.get("preset", "all")
    start = request.args.get("start")
    end = request.args.get("end")
    q = request.args.get("q", "").strip().upper()
    highlight = request.args.get("highlight")
    sort_by = request.args.get("sort_by", "newest").strip()

    start, end = apply_timeline_preset(preset, start, end)
    results = get_timeline_results(session["user_id"], start, end, q)

    results = sort_timeline_results(results, sort_by)

    # chart should use oldest -> newest
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

    chart_data = {
        "labels": labels,
        "ei": ei,
        "sn": sn,
        "tf": tf,
        "jp": jp
    }

    total = len(results)
    latest = results_sorted[-1] if total > 0 else None

    summary = {
        "total": total,
        "latest_type": latest["typeCode"] if latest else None,
        "latest_date": latest["createdAt"] if latest else None,
        "preset": preset,
        "start": start or "",
        "end": end or "",
        "q": q or "",
        "sort_by": sort_by
    }

    return render_template(
        "timeline.html",
        results=results,
        summary=summary,
        chart_data=chart_data,
        highlight=highlight
    )


# ======================================
# Send timeline email
# ======================================
@timeline_bp.post("/timeline/email", endpoint="send_timeline_email")
@login_required
def send_timeline_email():
    preset = (request.form.get("preset") or "all").strip()
    start = (request.form.get("start") or "").strip()
    end = (request.form.get("end") or "").strip()
    q = (request.form.get("q") or "").strip().upper()
    sort_by = (request.form.get("sort_by") or "newest").strip()

    to_email = (session.get("email") or "").strip().lower()
    if not to_email:
        msg = t_py("msg_no_email_found")
        return email_error_response(msg, 400, preset, start, end, q, sort_by, "error")

    start, end = apply_timeline_preset(preset, start, end)
    results = get_timeline_results(session["user_id"], start, end, q)

    results = sort_timeline_results(results, sort_by)

    if not results:
        msg = t_py("msg_no_timeline_results_for_email")
        return email_error_response(msg, 400, preset, start, end, q, sort_by, "warning")

    results_by_date = sorted(results, key=lambda r: parse_dt(r.get("createdAt")) or datetime.min)
    latest = results_by_date[-1] if results_by_date else None
    total = len(results)

    latest_type = latest.get("typeCode") if latest else "-"
    latest_date = latest.get("createdAt") if latest else "-"

    attachment_bytes = None
    attachment_filename = "timeline_charts.jpg"

    f = request.files.get("chart_file")
    if f and f.filename:
        attachment_bytes = f.read()
        attachment_filename = secure_filename(f.filename) or attachment_filename

    lang = get_lang()

    ok, msg = send_timeline_summary_email(
        to_email=to_email,
        lang=lang,
        total_results=total,
        latest_type=latest_type,
        latest_time=latest_date,
        filter_preset=preset,
        sort_by=sort_by,
        start=start,
        end=end,
        search=q,
        attachment_bytes=attachment_bytes,
        attachment_filename=attachment_filename
    )

    if is_fetch_request():
        response_msg = t_py("msg_email_sent_success") if ok else msg
        return jsonify({"ok": ok, "msg": response_msg}), (200 if ok else 500)

    flash(t_py("msg_email_sent_success") if ok else msg, "success" if ok else "error")
    return timeline_redirect(preset, start, end, q, sort_by)

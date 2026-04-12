import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# =========================
# SMTP Config
# =========================
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# =========================
# Language Helpers
# =========================
def normalize_lang(lang: str | None) -> str:
    if not lang:
        return "EN"

    lang = str(lang).strip().upper()

    if lang in {"EN", "ENG", "ENGLISH"}:
        return "EN"
    if lang in {"BM", "MS", "MALAY", "BAHASA", "BAHASA MELAYU"}:
        return "BM"
    if lang in {"ZH", "CN", "MANDARIN", "CHINESE", "中文", "华语"}:
        return "ZH"

    return "EN"

def is_valid_email(email: str) -> bool:
    return bool(email and EMAIL_REGEX.match(email.strip()))

# =========================
# Email Templates
# =========================
EMAIL_TEXTS = {
    "confirm_email": {
        "EN": {
            "subject": "Confirm your MBTI account",
            "body": """Hi,

Please confirm your account by clicking the link below:

{url}

If you did not register, please ignore this email.
"""
        },
        "BM": {
            "subject": "Sahkan akaun MBTI anda",
            "body": """Hai,

Sila sahkan akaun anda dengan menekan pautan di bawah:

{url}

Jika anda tidak mendaftar, sila abaikan e-mel ini.
"""
        },
        "ZH": {
            "subject": "请确认您的 MBTI 账号",
            "body": """您好，

请点击以下链接以确认您的账号：

{url}

如果您并未注册，请忽略此邮件。
"""
        }
    },

    "reset_password": {
        "EN": {
            "subject": "Reset your MBTI account password",
            "body": """Hi,

Click the link below to reset your password (expires in 30 minutes):

{url}

If you did not request this, please ignore this email.
"""
        },
        "BM": {
            "subject": "Tetapkan semula kata laluan akaun MBTI anda",
            "body": """Hai,

Klik pautan di bawah untuk menetapkan semula kata laluan anda (akan tamat tempoh dalam 30 minit):

{url}

Jika anda tidak membuat permintaan ini, sila abaikan e-mel ini.
"""
        },
        "ZH": {
            "subject": "重设您的 MBTI 账号密码",
            "body": """您好，

请点击以下链接以重设您的密码（30 分钟后失效）：

{url}

如果这不是您的请求，请忽略此邮件。
"""
        }
    },

    "timeline_summary": {
        "EN": {
            "subject": "Your MBTI Timeline Chart",
            "title": "MBTI Timeline Summary",
            "total_results": "Total results",
            "latest": "Latest",
            "filter_preset": "Filter preset",
            "sort_by": "Sort by",
            "date_range": "Date range",
            "search": "Search",
            "attachment_yes": "Your chart image is attached in this email.",
            "attachment_no": "Chart image was not included (capture/upload failed)."
        },
        "BM": {
            "subject": "Carta Garis Masa MBTI Anda",
            "title": "Ringkasan Garis Masa MBTI",
            "total_results": "Jumlah keputusan",
            "latest": "Terkini",
            "filter_preset": "Pratetap penapis",
            "sort_by": "Susun ikut",
            "date_range": "Julat tarikh",
            "search": "Carian",
            "attachment_yes": "Imej carta anda dilampirkan dalam e-mel ini.",
            "attachment_no": "Imej carta tidak disertakan (gagal tangkap/muat naik)."
        },
        "ZH": {
            "subject": "您的 MBTI 时间线图表",
            "title": "MBTI 时间线摘要",
            "total_results": "结果总数",
            "latest": "最新结果",
            "filter_preset": "筛选预设",
            "sort_by": "排序方式",
            "date_range": "日期范围",
            "search": "搜索",
            "attachment_yes": "您的图表图片已附在这封邮件中。",
            "attachment_no": "未附上图表图片（截图或上传失败）。"
        }
    }
}


# =========================
# Timeline display value translations
# =========================
TIMELINE_PRESET_LABELS = {
    "EN": {
        "all": "All",
        "7d": "Last 7 days",
        "30d": "Last 30 days",
        "12m": "Last 12 months",
    },
    "BM": {
        "all": "Semua",
        "7d": "7 hari terakhir",
        "30d": "30 hari terakhir",
        "12m": "12 bulan terakhir",
    },
    "ZH": {
        "all": "全部",
        "7d": "最近 7 天",
        "30d": "最近 30 天",
        "12m": "最近 12 个月",
    }
}

TIMELINE_SORT_LABELS = {
    "EN": {
        "newest": "Newest",
        "oldest": "Oldest",
        "type_asc": "Type A to Z",
        "type_desc": "Type Z to A",
        "conf_desc": "Confidence high to low",
        "conf_asc": "Confidence low to high",
    },
    "BM": {
        "newest": "Terkini ke terlama",
        "oldest": "Terlama ke terkini",
        "type_asc": "Jenis A ke Z",
        "type_desc": "Jenis Z ke A",
        "conf_desc": "Keyakinan tinggi ke rendah",
        "conf_asc": "Keyakinan rendah ke tinggi",
    },
    "ZH": {
        "newest": "最新到最旧",
        "oldest": "最旧到最新",
        "type_asc": "类型 A 到 Z",
        "type_desc": "类型 Z 到 A",
        "conf_desc": "置信度从高到低",
        "conf_asc": "置信度从低到高",
    }
}


def get_email_text(template_key: str, lang: str = "EN", **kwargs) -> tuple[str, str]:
    lang = normalize_lang(lang)

    template_group = EMAIL_TEXTS.get(template_key, {})
    template = template_group.get(lang) or template_group.get("EN", {})

    subject = template.get("subject", "").format(**kwargs)
    body = template.get("body", "").format(**kwargs)
    return subject, body


def get_timeline_preset_label(preset: str, lang: str) -> str:
    lang = normalize_lang(lang)
    return TIMELINE_PRESET_LABELS.get(lang, TIMELINE_PRESET_LABELS["EN"]).get(
        preset, preset
    )


def get_timeline_sort_label(sort_by: str, lang: str) -> str:
    lang = normalize_lang(lang)
    return TIMELINE_SORT_LABELS.get(lang, TIMELINE_SORT_LABELS["EN"]).get(
        sort_by, sort_by
    )


def build_timeline_email_content(
    lang: str,
    total_results: int,
    latest_type: str,
    latest_time: str,
    filter_preset: str,
    sort_by: str,
    start: str = "",
    end: str = "",
    search: str = "",
    has_attachment: bool = False
) -> tuple[str, str]:
    lang = normalize_lang(lang)
    template = EMAIL_TEXTS.get("timeline_summary", {}).get(lang) or EMAIL_TEXTS["timeline_summary"]["EN"]

    preset_label = get_timeline_preset_label(filter_preset, lang)
    sort_label = get_timeline_sort_label(sort_by, lang)

    lines = []
    lines.append(template["title"])
    lines.append("=" * 22)
    lines.append(f'{template["total_results"]}: {total_results}')
    latest_type_display = latest_type or "-"
    latest_time_display = latest_time or "-"
    lines.append(f'{template["latest"]}: {latest_type_display} ({latest_time_display})')
    lines.append(f'{template["filter_preset"]}: {preset_label}')
    lines.append(f'{template["sort_by"]}: {sort_label}')

    if start or end:
        lines.append(f'{template["date_range"]}: {start or "-"} -> {end or "-"}')

    if search:
        lines.append(f'{template["search"]}: {search}')

    lines.append("")
    lines.append(template["attachment_yes"] if has_attachment else template["attachment_no"])

    subject = template["subject"]
    body = "\n".join(lines)
    return subject, body

def _send_mime_message(
    msg,
    to_email: str,
    dev_label: str = "EMAIL"
) -> tuple[bool, str]:
    if not is_valid_email(to_email):
        return False, "Invalid recipient email"

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        print(f"=== {dev_label} (DEV MODE - NOT SENT) ===")
        print("To:", to_email)
        print("Subject:", msg.get("Subject", ""))
        print(msg.as_string())
        print("=========================================")
        return False, "SMTP not configured (DEV mode)"

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM, [to_email], msg.as_string())

        return True, "OK"
    except Exception as e:
        return False, f"SMTP send failed: {e}"

# =========================
# Basic Plain Email
# =========================
def send_plain_email(
    to_email: str,
    subject: str,
    body: str,
    dev_label: str = "EMAIL"
) -> tuple[bool, str]:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    return _send_mime_message(
        msg=msg,
        to_email=to_email,
        dev_label=dev_label
    )

# =========================
# Auth Emails
# =========================
def send_confirm_email(
    to_email: str,
    confirm_url: str,
    lang: str = "EN"
) -> tuple[bool, str]:
    subject, body = get_email_text(
        template_key="confirm_email",
        lang=lang,
        url=confirm_url
    )
    return send_plain_email(
        to_email=to_email,
        subject=subject,
        body=body,
        dev_label=f"CONFIRM LINK [{normalize_lang(lang)}]"
    )


def send_password_reset_email(
    to_email: str,
    reset_url: str,
    lang: str = "EN"
) -> tuple[bool, str]:
    subject, body = get_email_text(
        template_key="reset_password",
        lang=lang,
        url=reset_url
    )
    return send_plain_email(
        to_email=to_email,
        subject=subject,
        body=body,
        dev_label=f"RESET LINK [{normalize_lang(lang)}]"
    )


def send_timeline_summary_email(
    to_email: str,
    lang: str,
    total_results: int,
    latest_type: str,
    latest_time: str,
    filter_preset: str,
    sort_by: str,
    start: str = "",
    end: str = "",
    search: str = "",
    attachment_bytes: bytes | None = None,
    attachment_filename: str = "mbti_timeline.png"
) -> tuple[bool, str]:
    subject, body = build_timeline_email_content(
        lang=lang,
        total_results=total_results,
        latest_type=latest_type,
        latest_time=latest_time,
        filter_preset=filter_preset,
        sort_by=sort_by,
        start=start,
        end=end,
        search=search,
        has_attachment=bool(attachment_bytes)
    )

    return send_email_simple(
        to_email=to_email,
        subject=subject,
        body=body,
        attachment_bytes=attachment_bytes,
        attachment_filename=attachment_filename,
        dev_label=f"TIMELINE SUMMARY [{normalize_lang(lang)}]"
    )


# =========================
# General Email with Optional Attachment
# =========================
def send_email_simple(
    to_email: str,
    subject: str,
    body: str,
    attachment_bytes: bytes | None = None,
    attachment_filename: str = "attachment.bin",
    dev_label: str = "EMAIL"
) -> tuple[bool, str]:
    if attachment_bytes:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain", "utf-8"))

        part = MIMEApplication(attachment_bytes, Name=attachment_filename)
        part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
        msg.attach(part)
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    return _send_mime_message(
        msg=msg,
        to_email=to_email,
        dev_label=dev_label
    )
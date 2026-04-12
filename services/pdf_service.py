from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors

from i18n import TRANSLATIONS

# ======================================
# Translation-based MBTI profile loader
# ======================================
def get_mbti_profile_from_translations(type_code: str, lang: str) -> dict:
    lang = normalize_lang(lang)
    type_code = (type_code or "").upper()

    d = TRANSLATIONS.get(lang, TRANSLATIONS["EN"])

    intro = d.get(f"type_{type_code}_intro", "")
    tagline = d.get(f"type_{type_code}_tagline", "")

    strengths = [d.get(f"type_{type_code}_s{i}", "") for i in (1, 2, 3)]
    strengths = [x for x in strengths if x]

    weaknesses = [d.get(f"type_{type_code}_w{i}", "") for i in (1, 2, 3)]
    weaknesses = [x for x in weaknesses if x]

    return {
        "tagline": tagline,
        "intro": intro,
        "strengths": strengths,
        "weaknesses": weaknesses
    }

def normalize_lang(lang: str) -> str:
    lang = (lang or "EN").upper()
    return lang if lang in ("EN", "ZH", "BM") else "EN"

# ======================================
# Font registration
# ======================================
def ensure_pdf_font_registered(lang: str = "EN") -> str:
    font_name = "NotoSC"

    try:
        pdfmetrics.getFont(font_name)
        return font_name
    except KeyError:
        pass

    font_path = Path(__file__).resolve().parent.parent / "static" / "fonts" / "NotoSansSC-Regular.ttf"

    if font_path.exists():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
        return font_name

    # fallback font
    if (lang or "EN").upper() == "EN":
        return "Helvetica"

    # for ZH/BM mixed content, still try Helvetica if custom font missing
    # but Chinese may not display correctly, so this avoids crashing at least
    return "Helvetica"


# ======================================
# Avatar path
# ======================================
def get_mbti_avatar_path(type_code: str) -> Path:
    return Path(__file__).resolve().parent.parent / "static" / "img" / "mbti" / f"{type_code}.png"


# ======================================
# Basic text wrapping
# ======================================
def wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    if not text:
        return []

    text = str(text).strip()
    if not text:
        return [""]

    lines = []
    current = ""

    for ch in text:
        candidate = current + ch
        w = pdfmetrics.stringWidth(candidate, font_name, font_size)
        if w <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = ch

    if current:
        lines.append(current)

    return lines


# ======================================
# Color theme by MBTI group
# ======================================
def get_mbti_theme(type_code: str) -> dict:
    type_code = (type_code or "").upper()

    if len(type_code) >= 4:
        middle = type_code[1:3]
        if middle == "NT":
            return {
                "accent": colors.HexColor("#6D5BD0"),
                "accent_soft": colors.HexColor("#F4F1FF"),
                "accent_border": colors.HexColor("#D8D0FA"),
                "accent_text": colors.HexColor("#4C3FB1"),
                "muted_fill": colors.HexColor("#FAFAFC"),
                "soft_green": colors.HexColor("#ECFDF5"),
                "soft_green_border": colors.HexColor("#CFEFDE"),
                "soft_red": colors.HexColor("#FEF2F2"),
                "soft_red_border": colors.HexColor("#F6CACA"),
            }
        if middle == "NF":
            return {
                "accent": colors.HexColor("#2FA36B"),
                "accent_soft": colors.HexColor("#EDF9F2"),
                "accent_border": colors.HexColor("#CBEFD9"),
                "accent_text": colors.HexColor("#1D7A4E"),
                "muted_fill": colors.HexColor("#FAFCFB"),
                "soft_green": colors.HexColor("#ECFDF5"),
                "soft_green_border": colors.HexColor("#CFEFDE"),
                "soft_red": colors.HexColor("#FEF2F2"),
                "soft_red_border": colors.HexColor("#F6CACA"),
            }
        if middle == "SJ":
            return {
                "accent": colors.HexColor("#2D7FB8"),
                "accent_soft": colors.HexColor("#EEF6FB"),
                "accent_border": colors.HexColor("#CFE6F5"),
                "accent_text": colors.HexColor("#1F5F8D"),
                "muted_fill": colors.HexColor("#FAFCFE"),
                "soft_green": colors.HexColor("#ECFDF5"),
                "soft_green_border": colors.HexColor("#CFEFDE"),
                "soft_red": colors.HexColor("#FEF2F2"),
                "soft_red_border": colors.HexColor("#F6CACA"),
            }
        if middle == "SP":
            return {
                "accent": colors.HexColor("#D28A2D"),
                "accent_soft": colors.HexColor("#FFF6EC"),
                "accent_border": colors.HexColor("#F3DEBF"),
                "accent_text": colors.HexColor("#9A6117"),
                "muted_fill": colors.HexColor("#FFFDFC"),
                "soft_green": colors.HexColor("#ECFDF5"),
                "soft_green_border": colors.HexColor("#CFEFDE"),
                "soft_red": colors.HexColor("#FEF2F2"),
                "soft_red_border": colors.HexColor("#F6CACA"),
            }

    return {
        "accent": colors.HexColor("#4F46E5"),
        "accent_soft": colors.HexColor("#EEF2FF"),
        "accent_border": colors.HexColor("#C7D2FE"),
        "accent_text": colors.HexColor("#4338CA"),
        "muted_fill": colors.HexColor("#FAFAFC"),
        "soft_green": colors.HexColor("#ECFDF5"),
        "soft_green_border": colors.HexColor("#CFEFDE"),
        "soft_red": colors.HexColor("#FEF2F2"),
        "soft_red_border": colors.HexColor("#F6CACA"),
    }


# ======================================
# Scenario summary cleaner
# ======================================
def compact_scenario_summary(text: str, lang: str = "EN") -> list[str]:
    lang = normalize_lang(lang)
    raw_lines = [(x or "").strip() for x in (text or "").splitlines()]
    raw_lines = [x for x in raw_lines if x]

    skip_prefixes = {
        "EN": ["scenario test summary", "your answers"],
        "BM": ["ringkasan ujian senario", "jawapan anda"],
        "ZH": ["情境测试总结", "你的答案"],
    }.get(lang, ["scenario test summary", "your answers"])

    filtered = []
    for line in raw_lines:
        low = line.lower()
        if any(low.startswith(p) for p in skip_prefixes):
            continue
        filtered.append(line)

    result = []
    for line in filtered:
        for i in range(1, 21):
            line = line.replace(f"Q{i}:", "").strip()
        if len(line) > 100:
            line = line[:100].rstrip(" -:") + "..."
        if line:
            result.append(line)
        if len(result) >= 4:
            break

    return result


# ======================================
# Trait percentages
# ======================================
def estimate_trait_percentages(type_code: str, confidence: float) -> dict:
    type_code = (type_code or "INTP").upper()
    if len(type_code) != 4:
        type_code = "INTP"

    try:
        conf = float(confidence)
        if conf > 1:
            conf = conf / 100.0
    except Exception:
        conf = 0.75

    conf = max(0.50, min(conf, 0.99))

    dominant_pct = int(round((0.68 + ((conf - 0.50) * 0.40)) * 100))
    dominant_pct = max(68, min(dominant_pct, 89))
    opposite_pct = 100 - dominant_pct

    return {
        "EI": {
            type_code[0]: dominant_pct,
            ("E" if type_code[0] == "I" else "I"): opposite_pct,
        },
        "SN": {
            type_code[1]: dominant_pct,
            ("S" if type_code[1] == "N" else "N"): opposite_pct,
        },
        "TF": {
            type_code[2]: dominant_pct,
            ("F" if type_code[2] == "T" else "T"): opposite_pct,
        },
        "JP": {
            type_code[3]: dominant_pct,
            ("P" if type_code[3] == "J" else "J"): opposite_pct,
        },
    }

# ======================================
# Insight summary
# ======================================
def generate_personal_insight(type_code: str, lang: str = "EN") -> str:
    type_code = (type_code or "").upper()
    lang = normalize_lang(lang)

    if lang == "BM":
        return (
            f"Keputusan ini menunjukkan bahawa anda cenderung mempunyai gaya yang lebih tersusun, "
            f"praktikal, dan jelas dalam membuat keputusan. Profil {type_code} biasanya lebih selesa "
            f"dalam persekitaran yang mempunyai struktur, tanggungjawab yang jelas, dan hala tuju yang teratur. "
            f"Pada masa yang sama, keseimbangan juga boleh dipertingkatkan dengan memberi lebih ruang kepada fleksibiliti, "
            f"pandangan orang lain, dan pendekatan yang lebih terbuka."
        )

    if lang == "ZH":
        return (
            f"此结果显示，你的做事方式更偏向有条理、重视实际，并且在决策上较为明确。"
            f"{type_code} 型人格通常更适合目标清晰、职责明确、流程稳定的环境。"
            f"同时，你也可以进一步留意灵活性、他人感受，以及不同观点所带来的价值，"
            f"让整体表现更加平衡。"
        )

    return (
        f"This result suggests a stronger preference for structure, practical judgment, and clear execution. "
        f"Individuals with the {type_code} profile often feel more comfortable in environments where expectations, "
        f"roles, and goals are clearly defined. At the same time, overall balance can be improved by remaining open "
        f"to flexibility, alternative viewpoints, and the emotional needs of others."
    )


# ======================================
# Career fit summary
# ======================================
def make_career_fit_reason(title: str, desc: str, mbti_type: str, language: str) -> str:
    title = (title or "").strip()
    mbti_type = (mbti_type or "").upper()
    language = normalize_lang(language)

    simple_map = {
        "EN": {
            "Operations Manager": "Suitable for managing operations, coordinating tasks, and maintaining structure.",
            "Sales Manager": "Suitable for leading teams, setting goals, and driving results.",
            "Project Manager": "Suitable for planning tasks, organizing timelines, and overseeing progress.",
            "Accountant": "Suitable for handling records, reviewing details, and working accurately with numbers.",
        },
        "BM": {
            "Operations Manager": "Sesuai untuk mengurus operasi, menyelaras tugas, dan mengekalkan struktur kerja.",
            "Sales Manager": "Sesuai untuk memimpin pasukan, menetapkan sasaran, dan mencapai hasil.",
            "Project Manager": "Sesuai untuk merancang tugas, menyusun jadual, dan memantau kemajuan.",
            "Accountant": "Sesuai untuk mengendalikan rekod, menyemak butiran, dan bekerja dengan nombor secara teliti.",
        },
        "ZH": {
            "Operations Manager": "适合负责日常运营、协调任务并维持整体秩序。",
            "Sales Manager": "适合带领团队、设定目标并推动成果。",
            "Project Manager": "适合规划任务、安排进度并监督执行过程。",
            "Accountant": "适合处理记录、检查细节，并准确地处理数字工作。",
        }
    }

    lang_map = simple_map.get(language, simple_map["EN"])
    if title in lang_map:
        return lang_map[title]

    if language == "BM":
        return f"Peranan ini sesuai dengan kecenderungan {mbti_type} terhadap struktur, tanggungjawab, dan pelaksanaan kerja yang jelas."
    if language == "ZH":
        return f"这个方向较适合 {mbti_type} 在结构性、责任感与执行力方面的特点。"
    return f"This role suits the {mbti_type} preference for structure, responsibility, and clear execution."


# ======================================
# PDF builder
# ======================================
def build_result_pdf_bytes(
    type_code: str,
    confidence: float,
    scenario_summary_text: str,
    careers: list[dict],
    mbti_profile: dict,
    user_input_text: str = "",
    lang: str = "EN",
    created_at: str = ""
) -> bytes:
    lang = normalize_lang(lang)
    type_code = (type_code or "INTP").upper()
    if len(type_code) != 4:
        type_code = "INTP"

    font_name = ensure_pdf_font_registered(lang)
    theme = get_mbti_theme(type_code)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    PAGE_MARGIN = 16 * mm
    BOTTOM_MARGIN = 16 * mm

    margin = PAGE_MARGIN
    content_width = width - (2 * margin)
    y = height - PAGE_MARGIN

    LABELS = {
        "EN": {
            "report_title": "MBTI Personality Report",
            "report_subtitle": "Personality insight summary and career direction overview",
            "your_result": "Your Result",
            "confidence": "Confidence",
            "date": "Date",
            "language": "Language",
            "your_input": "Your Input",
            "scenario_summary": "Scenario Response Highlights",
            "personal_insight": "Personal Insight Summary",
            "personality_profile": "Personality Profile",
            "trait_balance": "Trait Balance",
            "key_traits": "Key Traits",
            "strengths": "Strengths",
            "weaknesses": "Growth Areas",
            "careers": "Recommended Career Directions",
            "no_careers": "No career recommendations available.",
            "bars": {
                "EI": ("Extraversion", "Introversion"),
                "SN": ("Sensing", "Intuition"),
                "TF": ("Thinking", "Feeling"),
                "JP": ("Judging", "Perceiving"),
            },
            "closing": "This report is generated to support self-exploration and career reflection.",
            "note": "Note: This report provides a prototype-level MBTI prediction for guidance and exploration. It should not be treated as a formal psychological assessment.",
        },
        "BM": {
            "report_title": "Laporan Personaliti MBTI",
            "report_subtitle": "Ringkasan personaliti dan gambaran arah kerjaya",
            "your_result": "Keputusan Anda",
            "confidence": "Keyakinan",
            "date": "Tarikh",
            "language": "Bahasa",
            "your_input": "Input Anda",
            "scenario_summary": "Sorotan Respons Senario",
            "personal_insight": "Ringkasan Pemerhatian Peribadi",
            "personality_profile": "Profil Personaliti",
            "trait_balance": "Keseimbangan Trait",
            "key_traits": "Ciri-ciri Utama",
            "strengths": "Kekuatan",
            "weaknesses": "Ruang Penambahbaikan",
            "careers": "Cadangan Arah Kerjaya",
            "no_careers": "Tiada cadangan kerjaya tersedia.",
            "bars": {
                "EI": ("Ekstroversi", "Introversi"),
                "SN": ("Penderiaan", "Intuisi"),
                "TF": ("Pemikiran", "Perasaan"),
                "JP": ("Berstruktur", "Fleksibel"),
            },
            "closing": "Laporan ini dihasilkan untuk menyokong penerokaan diri dan refleksi kerjaya.",
            "note": "Nota: Laporan ini memberikan ramalan MBTI peringkat prototaip untuk panduan dan penerokaan. Ia tidak sepatutnya dianggap sebagai penilaian psikologi formal.",
        },
        "ZH": {
            "report_title": "MBTI人格报告",
            "report_subtitle": "人格洞察摘要与职业方向概览",
            "your_result": "你的结果",
            "confidence": "置信度",
            "date": "日期",
            "language": "语言",
            "your_input": "你的输入",
            "scenario_summary": "情境回答摘要",
            "personal_insight": "个人洞察总结",
            "personality_profile": "人格简介",
            "trait_balance": "特质比例",
            "key_traits": "核心特质",
            "strengths": "优点",
            "weaknesses": "可成长方向",
            "careers": "推荐职业方向",
            "no_careers": "暂无职业推荐。",
            "bars": {
                "EI": ("外向", "内向"),
                "SN": ("实感", "直觉"),
                "TF": ("思考", "情感"),
                "JP": ("判断", "感知"),
            },
            "closing": "本报告用于支持自我探索与职业方向思考。",
            "note": "注：本报告提供的是原型级MBTI预测，用于参考与探索，不应视为正式心理测评。",
        },
    }

    T = LABELS[lang]

    # -----------------------------
    # helpers
    # -----------------------------
    def new_page():
        nonlocal y
        c.showPage()
        y = height - PAGE_MARGIN

    def ensure_space(required_height):
        nonlocal y
        if y - required_height < BOTTOM_MARGIN:
            new_page()

    def draw_text(text, x, y_pos, size=10, color=colors.black, font=None):
        c.setFillColor(color)
        c.setFont(font or font_name, size)
        c.drawString(x, y_pos, text or "")

    def draw_line(x1, y1, x2, y2, color=colors.HexColor("#E5E7EB"), width_value=0.8):
        c.setStrokeColor(color)
        c.setLineWidth(width_value)
        c.line(x1, y1, x2, y2)

    def draw_round_box(x, y_bottom, w, h, fill_color, stroke_color=None, radius=8, stroke_width=1):
        c.setFillColor(fill_color)
        c.setStrokeColor(stroke_color or fill_color)
        c.setLineWidth(stroke_width)
        c.roundRect(x, y_bottom, w, h, radius, fill=1, stroke=1)

    def draw_wrapped_text(text, x, y_pos, max_width, size=10, leading=12, color=colors.black, max_lines=None):
        c.setFillColor(color)
        c.setFont(font_name, size)

        lines = wrap_text(text or "", font_name, size, max_width)

        if max_lines is not None:
            lines = lines[:max_lines]

        cur_y = y_pos
        for line in lines:
            c.drawString(x, cur_y, line)
            cur_y -= leading
        return cur_y

    def section_title(title):
        nonlocal y
        ensure_space(12 * mm)
        draw_text(title, margin, y, size=13.2, color=colors.HexColor("#111827"))
        y -= 3.5 * mm
        draw_line(margin, y, width - margin, y, color=colors.HexColor("#E8EAF0"), width_value=0.8)
        y -= 5.5 * mm

    def draw_progress_bar(x, y_bottom, w, h, progress, fill_color, track_color):
        progress = max(0.0, min(1.0, progress))
        draw_round_box(x, y_bottom, w, h, track_color, track_color, radius=3, stroke_width=0.5)
        fill_w = max(2, w * progress)
        draw_round_box(x, y_bottom, fill_w, h, fill_color, fill_color, radius=3, stroke_width=0.5)

    # -----------------------------
    # Header
    # -----------------------------
    draw_text(T["report_title"], margin, y, size=20, color=colors.HexColor("#111827"))
    y -= 6 * mm
    draw_text(T["report_subtitle"], margin, y, size=9.2, color=colors.HexColor("#6B7280"))
    y -= 5 * mm
    draw_line(margin, y, width - margin, y, color=theme["accent"], width_value=1.2)
    y -= 8 * mm

    # -----------------------------
    # Main highlight card
    # -----------------------------
    card_h = 34 * mm
    ensure_space(card_h + 8 * mm)

    draw_round_box(
        margin, y - card_h, content_width, card_h,
        fill_color=theme["muted_fill"],
        stroke_color=colors.HexColor("#E6E8EE"),
        radius=10
    )

    avatar_x = margin + 6 * mm
    avatar_y = y - 25 * mm
    avatar_box = 22 * mm

    draw_round_box(
        avatar_x,
        avatar_y,
        avatar_box,
        avatar_box,
        fill_color=theme["accent_soft"],
        stroke_color=theme["accent_border"],
        radius=5
    )

    avatar_path = get_mbti_avatar_path(type_code)
    if avatar_path.exists():
        try:
            c.drawImage(
                str(avatar_path),
                avatar_x + 1 * mm,
                avatar_y + 1 * mm,
                width=20 * mm,
                height=20 * mm,
                preserveAspectRatio=True,
                mask="auto"
            )
        except Exception:
            pass

    text_x = avatar_x + 28 * mm
    draw_text(T["your_result"], text_x, y - 7 * mm, size=8.8, color=colors.HexColor("#6B7280"))
    draw_text(type_code, text_x, y - 16 * mm, size=24, color=colors.HexColor("#111827"))

    tagline = (mbti_profile.get("tagline") or "").strip()
    if tagline:
        draw_text(tagline, text_x, y - 23 * mm, size=9.3, color=theme["accent_text"])

    try:
        pct = round(float(confidence) * 100)
        pct_text = f"{pct}%"
    except Exception:
        pct_text = str(confidence)

    badge_w = 26 * mm
    badge_h = 9 * mm
    badge_x = text_x + 38 * mm
    badge_y = y - 16.5 * mm

    draw_round_box(
        badge_x, badge_y, badge_w, badge_h,
        fill_color=theme["accent_soft"],
        stroke_color=theme["accent_border"],
        radius=5
    )
    draw_text(f"{T['confidence']} {pct_text}", badge_x + 3.5 * mm, badge_y + 3 * mm, size=7.9, color=theme["accent_text"])

    info_x = margin + content_width - 48 * mm
    draw_text(f"{T['date']}: {created_at or '-'}", info_x, y - 9 * mm, size=8.1, color=colors.HexColor("#4B5563"))
    draw_text(f"{T['language']}: {lang}", info_x, y - 17 * mm, size=8.1, color=colors.HexColor("#4B5563"))

    y -= card_h + 10 * mm

    # -----------------------------
    # Personal insight summary
    # -----------------------------
    section_title(T["personal_insight"])

    insight = generate_personal_insight(type_code, lang)
    insight_box_h = 23 * mm
    ensure_space(insight_box_h + 5 * mm)

    draw_round_box(
        margin, y - insight_box_h, content_width, insight_box_h,
        fill_color=theme["accent_soft"],
        stroke_color=theme["accent_border"],
        radius=8
    )

    draw_wrapped_text(
        insight,
        margin + 6 * mm,
        y - 7 * mm,
        content_width - 12 * mm,
        size=9.1,
        leading=10.5,
        color=colors.HexColor("#374151"),
        max_lines=4
    )

    y -= insight_box_h + 8 * mm

    # -----------------------------
    # Scenario highlights
    # -----------------------------
    compact_summary = compact_scenario_summary(scenario_summary_text, lang)
    if compact_summary:
        section_title(T["scenario_summary"])

        for line in compact_summary:
            ensure_space(7 * mm)
            draw_text("•", margin + 2 * mm, y, size=10, color=theme["accent_text"])
            draw_wrapped_text(
                line,
                margin + 7 * mm,
                y,
                content_width - 12 * mm,
                size=8.9,
                leading=10,
                color=colors.HexColor("#374151"),
                max_lines=2
            )
            y -= 6.3 * mm

        y -= 2 * mm

    # -----------------------------
    # Optional user input
    # -----------------------------
    if user_input_text:
        section_title(T["your_input"])

        draw_wrapped_text(
            f"“{user_input_text.strip()}”",
            margin,
            y,
            content_width,
            size=9.0,
            leading=10.5,
            color=colors.HexColor("#374151"),
            max_lines=4
        )
        y -= 12 * mm

    # -----------------------------
    # Personality profile
    # -----------------------------
    section_title(T["personality_profile"])

    intro = (mbti_profile.get("intro") or "").strip()
    profile_header = type_code if not tagline else f"{type_code} — {tagline}"

    draw_text(profile_header, margin, y, size=11.7, color=colors.HexColor("#111827"))
    y -= 6 * mm

    draw_wrapped_text(
        intro,
        margin,
        y,
        content_width,
        size=9.0,
        leading=10.5,
        color=colors.HexColor("#374151"),
        max_lines=5
    )
    y -= 14 * mm

    # -----------------------------
    # Trait balance
    # -----------------------------
    section_title(T["trait_balance"])

    trait_percentages = estimate_trait_percentages(type_code, confidence)
    pair_labels = T["bars"]

    pair_defs = [
        ("EI", type_code[0], "E" if type_code[0] == "I" else "I", pair_labels["EI"][0], pair_labels["EI"][1]),
        ("SN", type_code[1], "S" if type_code[1] == "N" else "N", pair_labels["SN"][0], pair_labels["SN"][1]),
        ("TF", type_code[2], "F" if type_code[2] == "T" else "T", pair_labels["TF"][0], pair_labels["TF"][1]),
        ("JP", type_code[3], "P" if type_code[3] == "J" else "J", pair_labels["JP"][0], pair_labels["JP"][1]),
    ]

    ensure_space(36 * mm)

    col_gap = 12 * mm
    col_w = (content_width - col_gap) / 2
    row_gap = 12 * mm

    start_x_left = margin
    start_x_right = margin + col_w + col_gap
    start_y = y

    positions = [
        (start_x_left, start_y, pair_defs[0]),
        (start_x_right, start_y, pair_defs[1]),
        (start_x_left, start_y - row_gap, pair_defs[2]),
        (start_x_right, start_y - row_gap, pair_defs[3]),
    ]

    for base_x, base_y, (pair_key, dominant_letter, opposite_letter, left_label, right_label) in positions:
        dominant_pct = trait_percentages[pair_key][dominant_letter]
        opposite_pct = trait_percentages[pair_key][opposite_letter]

        draw_text(f"{dominant_letter} {dominant_pct}%", base_x, base_y, size=9.0, color=theme["accent_text"])
        draw_text(f"{opposite_letter} {opposite_pct}%", base_x + 52 * mm, base_y, size=9.0, color=colors.HexColor("#6B7280"))

        draw_text(left_label, base_x, base_y - 5 * mm, size=7.8, color=colors.HexColor("#4B5563"))
        draw_text(right_label, base_x + 52 * mm, base_y - 5 * mm, size=7.8, color=colors.HexColor("#4B5563"))

        draw_progress_bar(
            base_x + 17 * mm,
            base_y - 6.8 * mm,
            32 * mm,
            3.7 * mm,
            dominant_pct / 100.0,
            theme["accent"],
            colors.HexColor("#E5E7EB")
        )

    y -= 31 * mm

    # -----------------------------
    # Key traits
    # -----------------------------
    section_title(T["key_traits"])

    strengths = mbti_profile.get("strengths") or []
    weaknesses = mbti_profile.get("weaknesses") or []

    box_h = 42 * mm
    col_gap = 8 * mm
    col_w = (content_width - col_gap) / 2
    ensure_space(box_h + 6 * mm)

    left_x = margin
    right_x = margin + col_w + col_gap
    bottom_y = y - box_h

    draw_round_box(
        left_x, bottom_y, col_w, box_h,
        fill_color=theme["soft_green"],
        stroke_color=theme["soft_green_border"],
        radius=8
    )
    draw_round_box(
        right_x, bottom_y, col_w, box_h,
        fill_color=theme["soft_red"],
        stroke_color=theme["soft_red_border"],
        radius=8
    )

    draw_text(T["strengths"], left_x + 5 * mm, y - 6 * mm, size=10.2, color=colors.HexColor("#065F46"))
    draw_text(T["weaknesses"], right_x + 5 * mm, y - 6 * mm, size=10.2, color=colors.HexColor("#991B1B"))

    sy = y - 13 * mm
    for item in strengths[:3]:
        lines = wrap_text(item, font_name, 8.3, col_w - 10 * mm)
        if lines:
            draw_text(f"• {lines[0]}", left_x + 5 * mm, sy, size=8.3, color=colors.HexColor("#374151"))
            sy -= 4.4 * mm
            for extra in lines[1:2]:
                draw_text(f"  {extra}", left_x + 5 * mm, sy, size=8.0, color=colors.HexColor("#374151"))
                sy -= 4.0 * mm
            sy -= 0.8 * mm

    wy = y - 13 * mm
    for item in weaknesses[:3]:
        lines = wrap_text(item, font_name, 8.3, col_w - 10 * mm)
        if lines:
            draw_text(f"• {lines[0]}", right_x + 5 * mm, wy, size=8.3, color=colors.HexColor("#374151"))
            wy -= 4.4 * mm
            for extra in lines[1:2]:
                draw_text(f"  {extra}", right_x + 5 * mm, wy, size=8.0, color=colors.HexColor("#374151"))
                wy -= 4.0 * mm
            wy -= 0.8 * mm

    y -= box_h + 10 * mm

    # -----------------------------
    # Careers
    # -----------------------------
    section_title(T["careers"])

    if not careers:
        draw_text(T["no_careers"], margin, y, size=9.2, color=colors.HexColor("#6B7280"))
        y -= 8 * mm
    else:
        for i, car in enumerate(careers[:4], start=1):
            title = (car.get("title") or car.get("careerKey") or "").strip()
            desc = (car.get("description") or "").strip()
            fit_reason = make_career_fit_reason(title, desc, type_code, lang)

            ensure_space(15 * mm)

            draw_text(f"{i}. {title}", margin, y, size=10.7, color=colors.HexColor("#111827"))
            y -= 5.5 * mm

            draw_wrapped_text(
                fit_reason,
                margin + 5 * mm,
                y,
                content_width - 5 * mm,
                size=8.8,
                leading=10,
                color=colors.HexColor("#374151"),
                max_lines=3
            )
            y -= 10.5 * mm

    # -----------------------------
    # Footer note
    # -----------------------------
    ensure_space(20 * mm)
    draw_line(margin, y, width - margin, y, color=colors.HexColor("#E5E7EB"), width_value=0.8)
    y -= 6 * mm

    draw_text(T["closing"], margin, y, size=8.4, color=colors.HexColor("#4B5563"))
    y -= 5.5 * mm

    draw_wrapped_text(
        T["note"],
        margin,
        y,
        content_width,
        size=7.4,
        leading=8.5,
        color=colors.HexColor("#6B7280"),
        max_lines=3
    )

    c.save()
    return buf.getvalue()
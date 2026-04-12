import os
import re
from typing import List, Dict, Tuple

import cv2
import numpy as np
import pdfplumber
import pytesseract
from pdf2image import convert_from_path


# ======================================
# Tesseract / Poppler configuration
# ======================================
# Update these paths if installed elsewhere.
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\Release-25.12.0-0\poppler-25.12.0\Library\bin"


# ======================================
# File helpers
# ======================================
def get_file_ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def allowed_resume_extension(filename: str) -> bool:
    return get_file_ext(filename) in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


# ======================================
# PDF helpers
# ======================================
def convert_pdf_to_images(pdf_path: str, dpi: int = 300) -> List[str]:
    """
    Convert each page of a PDF into PNG images.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    pages = convert_from_path(pdf_path, dpi=dpi, poppler_path=POPPLER_PATH)
    output_paths: List[str] = []

    for i, page in enumerate(pages, start=1):
        out_path = f"{pdf_path}_page_{i}.png"
        page.save(out_path, "PNG")
        output_paths.append(out_path)

    return output_paths


def extract_text_from_pdf_direct(pdf_path: str) -> str:
    """
    Extract text directly from a digital PDF without OCR.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    texts: List[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            page_text = clean_ocr_text(page_text)
            if page_text.strip():
                texts.append(page_text.strip())

    return "\n\n".join(texts).strip()


def is_meaningful_pdf_text(text: str) -> bool:
    """
    Decide whether direct PDF extraction is good enough to use.
    """
    if not text or len(text.strip()) < 120:
        return False

    return score_ocr_text(text) >= 250


# ======================================
# OCR text cleaning / scoring
# ======================================
def clean_ocr_text(text: str) -> str:
    """
    Normalize OCR text and reduce common OCR noise.
    """
    if not text:
        return ""

    replacements = {
        "\uFFFE": "",
        "￾": "",
        "\ufeff": "",
        "\xa0": " ",
        "•": "o ",
        "●": "o ",
        "◦": "o ",
        "▪": "o ",
        "◆": "o ",
        "■": "o ",
        "©": "o ",
        "®": "o ",
        "™": "",
        "|": " ",
    }

    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # Normalize common section OCR corruption
    section_repairs = {
        r"\bqanguages\b": "languages",
        r"\blanguages?\b": "languages",
        r"\bskints\b": "skills",
        r"\bskllls\b": "skills",
        r"\bskiils\b": "skills",
        r"\binterasts\b": "interests",
        r"\beducati0n\b": "education",
        r"\bexperlence\b": "experience",
        r"\bwork experlence\b": "work experience",
        r"\bconfer?nces?\b": "conferences",
        r"\bc0urses\b": "courses",
    }
    lower_for_repair = text.lower()
    for pattern, replacement in section_repairs.items():
        lower_for_repair = re.sub(pattern, replacement, lower_for_repair, flags=re.IGNORECASE)

    text = lower_for_repair

    # Fix line breaks inside words
    text = re.sub(r"([A-Za-z])\n([a-z])", r"\1 \2", text)
    text = re.sub(r"([0-9])\n([0-9])", r"\1\2", text)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove lines that are only punctuation
    lines = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            lines.append("")
            continue
        if re.fullmatch(r"[\W_]+", cleaned):
            continue
        lines.append(cleaned)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def score_ocr_text(text: str) -> int:
    """
    Heuristic score for OCR quality / resume-likeness.
    """
    if not text:
        return 0

    score = 0
    lower_text = text.lower()

    score += min(len(text), 2000)
    score += len(re.findall(r"[A-Za-z]", text))
    score += 50 * len(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))
    score += 30 * len(re.findall(r"(\+?\d[\d\s\-()]{7,}\d)", text))

    important_keywords = [
        "education", "skills", "experience", "work experience", "employment",
        "project", "projects", "internship", "intern", "summary", "profile",
        "objective", "contact", "languages", "reference", "references",
        "achievements", "certification", "courses", "university", "college",
        "sales", "marketing", "business", "accounting", "finance", "customer service"
    ]
    for kw in important_keywords:
        if kw in lower_text:
            score += 40

    junk_penalties = [
        "menu", "receipt", "invoice", "discount", "promotion", "bill",
        "question 1", "chapter 1", "official receipt", "price", "subtotal"
    ]
    for kw in junk_penalties:
        if kw in lower_text:
            score -= 80

    return score


# ======================================
# Image preprocessing
# ======================================
def get_image_quality_scores(image_path: str) -> Dict[str, float]:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Unable to read image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    return {
        "width": int(gray.shape[1]),
        "height": int(gray.shape[0]),
        "brightness": float(np.mean(gray)),
        "blur_score": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
    }


def preprocess_resume_image(image_path: str) -> str:
    """
    Strong preprocessing for camera / JPG resume images.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Unable to read image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    # denoise
    gray = cv2.bilateralFilter(gray, 7, 50, 50)

    # adaptive threshold
    thresh = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15
    )

    if np.mean(thresh) < 127:
        thresh = 255 - thresh

    kernel = np.ones((1, 1), np.uint8)
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)

    output_path = image_path.rsplit(".", 1)[0] + "_processed.png"
    cv2.imwrite(output_path, cleaned)
    return output_path


def preprocess_resume_image_light(image_path: str) -> str:
    """
    Lighter preprocessing for already clean images / PDF-converted pages.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Unable to read image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)

    output_path = image_path.rsplit(".", 1)[0] + "_light_processed.png"
    cv2.imwrite(output_path, gray)
    return output_path


# ======================================
# OCR helpers
# ======================================
def extract_text_from_image(image_path: str, lang: str = "eng") -> str:
    """
    OCR a single image with multiple Tesseract configs and keep the best result.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    configs = [
        "--oem 3 --psm 4",
        "--oem 3 --psm 6",
        "--oem 3 --psm 3",
        "--oem 3 --psm 11",
    ]

    best_text = ""
    best_score = -1

    for cfg in configs:
        try:
            text = pytesseract.image_to_string(image_path, lang=lang, config=cfg)
            text = clean_ocr_text(text)
            score = score_ocr_text(text)

            if score > best_score:
                best_score = score
                best_text = text
        except Exception:
            pass

    return best_text.strip()


def split_two_column_image(image_path: str) -> Tuple[str, str]:
    """
    Split an image into left and right regions for two-column resume OCR.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Unable to read image: {image_path}")

    h, w = img.shape[:2]
    split_x = int(w * 0.34)

    left = img[:, :split_x]
    right = img[:, split_x:]

    left_path = image_path.rsplit(".", 1)[0] + "_left.png"
    right_path = image_path.rsplit(".", 1)[0] + "_right.png"

    cv2.imwrite(left_path, left)
    cv2.imwrite(right_path, right)

    return left_path, right_path


def extract_text_from_two_column_image(image_path: str, lang: str = "eng") -> str:
    left_path, right_path = split_two_column_image(image_path)

    left_processed = preprocess_resume_image(left_path)
    right_processed = preprocess_resume_image(right_path)

    left_text = extract_text_from_image(left_processed, lang=lang)
    right_text = extract_text_from_image(right_processed, lang=lang)

    combined = "\n\n".join([t for t in [left_text, right_text] if t.strip()])
    return clean_ocr_text(combined)


def extract_text_from_resume_pages(image_paths: List[str], lang: str = "eng") -> str:
    """
    OCR all pages/images and combine results.
    For each page, compare whole-page OCR and two-column OCR and keep the better one.
    """
    texts: List[str] = []

    for image_path in image_paths:
        # Try strong preprocessing
        whole_processed = preprocess_resume_image(image_path)
        whole_text = extract_text_from_image(whole_processed, lang=lang)
        whole_score = score_ocr_text(whole_text)

        # Try light preprocessing too
        light_processed = preprocess_resume_image_light(image_path)
        light_text = extract_text_from_image(light_processed, lang=lang)
        light_score = score_ocr_text(light_text)

        # Try two-column OCR
        try:
            two_col_text = extract_text_from_two_column_image(image_path, lang=lang)
            two_col_score = score_ocr_text(two_col_text)
        except Exception:
            two_col_text = ""
            two_col_score = -1

        candidates = [
            (whole_text, whole_score),
            (light_text, light_score),
            (two_col_text, two_col_score),
        ]
        best_text, _ = max(candidates, key=lambda x: x[1])
        best_text = clean_ocr_text(best_text)

        if best_text.strip():
            texts.append(best_text.strip())

    return "\n\n".join(texts).strip()


def extract_text_from_resume_file(file_path: str, lang: str = "eng") -> str:
    """
    Main extraction helper.
    """
    ext = get_file_ext(file_path)

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return extract_text_from_resume_pages([file_path], lang=lang)

    if ext == ".pdf":
        # First try direct PDF text extraction
        try:
            direct_text = extract_text_from_pdf_direct(file_path)
            if is_meaningful_pdf_text(direct_text):
                return direct_text
        except Exception:
            pass

        # Fallback to OCR
        image_paths = convert_pdf_to_images(file_path)
        return extract_text_from_resume_pages(image_paths, lang=lang)

    raise ValueError("Unsupported resume file type. Only PDF, PNG, JPG, JPEG, WEBP are allowed.")


# ======================================
# Resume relevance validation
# ======================================
RESUME_KEYWORDS = {
    # English
    "resume", "cv", "education", "skills", "experience", "work experience",
    "employment", "project", "projects", "internship", "intern", "summary",
    "profile", "objective", "contact", "email", "phone", "reference",
    "references", "achievement", "achievements", "activities", "language",
    "languages", "sales", "marketing", "business", "customer service",
    "accounting", "finance", "degree", "diploma", "university", "college",

    # Malay
    "resume", "pendidikan", "kemahiran", "pengalaman", "pengalaman kerja",
    "projek", "latihan industri", "pensijilan", "profil", "ringkasan",
    "objektif", "emel", "telefon", "rujukan", "pencapaian", "aktiviti",
    "bahasa", "jualan", "pemasaran", "perniagaan", "ijazah", "diploma",

    # Mandarin
    "简历", "履历", "教育", "技能", "经验", "工作经验", "项目", "实习",
    "证书", "认证", "个人简介", "简介", "求职目标", "邮箱", "电话",
    "联系方式", "成就", "活动", "语言", "销售", "市场", "商业", "学士", "文凭"
}

NON_RESUME_KEYWORDS = {
    "menu", "receipt", "invoice", "promotion", "discount", "chapter",
    "assignment", "exam", "question", "poster", "advertisement", "welcome",
    "total", "price", "rm", "official receipt", "bill",
    "lecture", "tutorial", "lab", "semester", "student id", "course code",
    "reference list", "bibliography", "introduction", "conclusion",
    "abstract", "appendix", "table of contents", "figure", "diagram",
    "answer", "mark", "marks", "score", "test paper", "worksheet",
    "homework", "exercise", "university assignment", "class note", "notes"
}


def validate_resume_text_relevance(text: str) -> Dict[str, object]:
    clean_text = (text or "").strip()
    lower_text = clean_text.lower()

    score = 0
    reasons: List[str] = []

    word_count = len(re.findall(r"\b\w+\b", lower_text))
    char_count = len(clean_text)

    if char_count >= 120:
        score += 2
    else:
        reasons.append("too_little_text")

    if word_count >= 20:
        score += 1
    else:
        reasons.append("too_few_words")

    found_resume_keywords = [kw for kw in RESUME_KEYWORDS if kw.lower() in lower_text]
    found_non_resume_keywords = [kw for kw in NON_RESUME_KEYWORDS if kw.lower() in lower_text]

    if len(found_resume_keywords) >= 3:
        score += 3
    elif len(found_resume_keywords) >= 1:
        score += 1
    else:
        reasons.append("no_resume_keywords")

    email_found = bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", clean_text))
    phone_found = bool(re.search(r"(\+?\d[\d\s\-()]{7,}\d)", clean_text))

    if email_found:
        score += 2
    if phone_found:
        score += 1

    if len(found_non_resume_keywords) >= 2:
        score -= 2
        reasons.append("too_many_non_resume_keywords")

    is_valid = score >= 4

    return {
        "valid": is_valid,
        "score": score,
        "reasons": reasons,
        "resume_keywords_found": found_resume_keywords,
        "non_resume_keywords_found": found_non_resume_keywords,
        "email_found": email_found,
        "phone_found": phone_found,
        "char_count": char_count,
        "word_count": word_count,
    }
    
def validate_ocr_readability(raw_text: str) -> Dict[str, object]:
    """
    Check whether OCR text is readable enough for reliable resume extraction.
    This is separate from 'is this a resume?'.
    """
    text = clean_ocr_text(raw_text or "")
    if not text.strip():
        return {
            "valid": False,
            "reason": "empty_text",
            "char_count": 0,
            "word_count": 0,
            "noise_ratio": 1.0,
        }

    char_count = len(text)
    word_count = len(re.findall(r"\b\w+\b", text))
    alnum_count = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text))
    total_nonspace = len(re.sub(r"\s+", "", text))

    noise_ratio = 1.0
    if total_nonspace > 0:
        noise_ratio = 1 - (alnum_count / total_nonspace)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    long_lines = [ln for ln in lines if len(ln) >= 20]

    if char_count < 60:
        return {
            "valid": False,
            "reason": "too_little_text",
            "char_count": char_count,
            "word_count": word_count,
            "noise_ratio": noise_ratio,
        }

    if word_count < 10:
        return {
            "valid": False,
            "reason": "too_few_words",
            "char_count": char_count,
            "word_count": word_count,
            "noise_ratio": noise_ratio,
        }

    if noise_ratio > 0.55:
        return {
            "valid": False,
            "reason": "too_noisy",
            "char_count": char_count,
            "word_count": word_count,
            "noise_ratio": noise_ratio,
        }

    if len(long_lines) < 2:
        return {
            "valid": False,
            "reason": "too_fragmented",
            "char_count": char_count,
            "word_count": word_count,
            "noise_ratio": noise_ratio,
        }

    return {
        "valid": True,
        "reason": "",
        "char_count": char_count,
        "word_count": word_count,
        "noise_ratio": noise_ratio,
    }
    
CAPTURE_QUALITY_ERROR_KEY = "resume_capture_quality_error"
CAPTURE_QUALITY_ERROR_MESSAGE = (
    "The photo is too blurry, too dark, or unclear to read reliably. "
    "Please retake a clear photo of your resume only."
)

def looks_like_document_image(image_path: str) -> bool:
    """
    Soft hint only. Do not rely on this alone for final rejection.
    """
    if not os.path.exists(image_path):
        return False

    img = cv2.imread(image_path)
    if img is None:
        return False

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_area = gray.shape[0] * gray.shape[1]

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.12:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) == 4:
            return True

    return False


def validate_resume_image(image_path: str, lang: str = "eng") -> Dict[str, object]:
    quality = get_image_quality_scores(image_path)
    document_hint = looks_like_document_image(image_path)

    if quality["width"] < 500 or quality["height"] < 700:
        return {
            "valid": False,
            "error_key": CAPTURE_QUALITY_ERROR_KEY,
            "message": CAPTURE_QUALITY_ERROR_MESSAGE,
            "quality": quality,
            "raw_text": "",
            "document_hint": document_hint,
            "reason": "low_resolution",
        }

    if quality["brightness"] < 25:
        return {
            "valid": False,
            "error_key": CAPTURE_QUALITY_ERROR_KEY,
            "message": CAPTURE_QUALITY_ERROR_MESSAGE,
            "quality": quality,
            "raw_text": "",
            "document_hint": document_hint,
            "reason": "too_dark",
        }

    if quality["blur_score"] < 20:
        return {
            "valid": False,
            "error_key": CAPTURE_QUALITY_ERROR_KEY,
            "message": CAPTURE_QUALITY_ERROR_MESSAGE,
            "quality": quality,
            "raw_text": "",
            "document_hint": document_hint,
            "reason": "too_blurry",
        }

    raw_text = extract_text_from_resume_pages([image_path], lang=lang)
    readability = validate_ocr_readability(raw_text)
    relevance = validate_resume_text_relevance(raw_text)

    if not readability["valid"]:
        return {
            "valid": False,
            "error_key": CAPTURE_QUALITY_ERROR_KEY,
            "message": CAPTURE_QUALITY_ERROR_MESSAGE,
            "quality": quality,
            "raw_text": raw_text,
            "readability": readability,
            "relevance": relevance,
            "document_hint": document_hint,
            "reason": readability["reason"],
        }

    # Important: if it looks like a document but OCR resume keywords are weak,
    # still treat it as quality issue, not "not resume"
    if not relevance["valid"]:
        resume_kw_count = len(relevance.get("resume_keywords_found", []))
        non_resume_kw_count = len(relevance.get("non_resume_keywords_found", []))
        char_count = readability.get("char_count", 0)

        # clear readable text + strong non-resume signals => not resume
        if readability["valid"] and non_resume_kw_count >= 1 and resume_kw_count == 0:
            return {
                "valid": False,
                "error_key": "resume_not_relevant",
                "message": "The image does not appear to be a resume.",
                "quality": quality,
                "raw_text": raw_text,
                "relevance": relevance,
                "readability": readability,
                "document_hint": document_hint,
                "reason": "not_resume",
            }

        # very readable but still no resume evidence => not resume
        if readability["valid"] and resume_kw_count == 0 and char_count >= 120:
            return {
                "valid": False,
                "error_key": "resume_not_relevant",
                "message": "The image does not appear to be a resume.",
                "quality": quality,
                "raw_text": raw_text,
                "relevance": relevance,
                "readability": readability,
                "document_hint": document_hint,
                "reason": "not_resume",
            }

        # otherwise treat as unclear capture / weak OCR
        return {
            "valid": False,
            "error_key": CAPTURE_QUALITY_ERROR_KEY,
            "message": CAPTURE_QUALITY_ERROR_MESSAGE,
            "quality": quality,
            "raw_text": raw_text,
            "relevance": relevance,
            "readability": readability,
            "document_hint": document_hint,
            "reason": "unclear_resume_text",
        }


def validate_resume_text_only(raw_text: str) -> Dict[str, object]:
    text = clean_ocr_text(raw_text or "")
    readability = validate_ocr_readability(text)

    if not readability["valid"]:
        return {
            "valid": False,
            "error_key": CAPTURE_QUALITY_ERROR_KEY,
            "message": CAPTURE_QUALITY_ERROR_MESSAGE,
            "readability": readability,
        }

    relevance = validate_resume_text_relevance(text)

    if not relevance["valid"]:
        resume_kw_count = len(relevance.get("resume_keywords_found", []))
        non_resume_kw_count = len(relevance.get("non_resume_keywords_found", []))
        char_count = readability.get("char_count", 0)

    if non_resume_kw_count >= 1 and resume_kw_count == 0 and char_count >= 100:
        return {
            "valid": False,
            "error_key": "resume_not_relevant",
            "message": "The file does not appear to be a resume.",
            "relevance": relevance,
            "readability": readability,
        }

    return {
        "valid": False,
        "error_key": CAPTURE_QUALITY_ERROR_KEY,
        "message": CAPTURE_QUALITY_ERROR_MESSAGE,
        "relevance": relevance,
        "readability": readability,
    }

# ======================================
# Section helpers
# ======================================
SECTION_PATTERNS = {
    "summary": [
        r"\bsummary\b", r"\bprofile\b", r"\bprofessional summary\b", r"\bobjective\b",
        r"\b个人简介\b", r"\b简介\b", r"\b求职目标\b",
        r"\bringkasan\b", r"\bprofil\b", r"\bobjektif\b",
    ],
    "skills": [
        r"\bskills\b", r"\btechnical skills\b", r"\bcore competencies\b",
        r"\b技能\b",
        r"\bkemahiran\b",
    ],
    "education": [
        r"\beducation\b", r"\bacademic background\b",
        r"\b教育\b",
        r"\bpendidikan\b",
    ],
    "languages": [
        r"\blanguages\b", r"\blanguage\b",
        r"\b语言\b",
        r"\bbahasa\b",
    ],
    "interests": [
        r"\binterests\b", r"\bhobbies\b",
        r"\b兴趣\b", r"\b爱好\b",
        r"\bminat\b", r"\bhobi\b",
    ],
    "work_experience": [
        r"\bwork experience\b", r"\bexperience\b", r"\bemployment\b", r"\bprofessional experience\b",
        r"\b工作经验\b", r"\b经历\b",
        r"\bpengalaman kerja\b", r"\bpengalaman\b",
    ],
    "courses": [
        r"\bcourses\b", r"\bcertifications\b", r"\bconferences\b",
        r"\b课程\b", r"\b证书\b", r"\b认证\b",
        r"\bkursus\b", r"\bpensijilan\b",
    ]
}


def _find_section_positions(text: str) -> List[Tuple[int, str]]:
    positions: List[Tuple[int, str]] = []
    lower_text = text.lower()

    for section_name, patterns in SECTION_PATTERNS.items():
        for pat in patterns:
            match = re.search(pat, lower_text, flags=re.IGNORECASE)
            if match:
                positions.append((match.start(), section_name))
                break

    positions.sort(key=lambda x: x[0])
    return positions


def split_resume_sections(text: str) -> Dict[str, str]:
    """
    Split OCR resume text into rough sections by headings.
    """
    clean_text = clean_ocr_text(text)
    positions = _find_section_positions(clean_text)

    if not positions:
        return {"full_text": clean_text}

    sections: Dict[str, str] = {}
    for idx, (start_pos, section_name) in enumerate(positions):
        end_pos = positions[idx + 1][0] if idx + 1 < len(positions) else len(clean_text)
        chunk = clean_text[start_pos:end_pos].strip()
        sections[section_name] = chunk

    sections["full_text"] = clean_text
    return sections


# ======================================
# Parsing helpers
# ======================================
FIELD_OF_STUDY_KEYWORDS = {
    "Computer Science": [
        # English
        "computer science", "computing", "computer studies",
        # Malay
        "sains komputer",
        # Mandarin
        "计算机科学", "电脑科学"
    ],
    "Software Engineering": [
        "software engineering", "software engineer", "software development",
        "kejuruteraan perisian",
        "软件工程", "软件开发"
    ],
    "Data Science": [
        "data science", "data analytics", "analytics", "big data",
        "sains data", "analitik data",
        "数据科学", "数据分析"
    ],
    "Information Technology": [
        "information technology", "information systems",
        "teknologi maklumat", "sistem maklumat",
        "信息技术", "资讯科技", "信息系统"
    ],
    "Cybersecurity": [
        "cybersecurity", "cyber security", "information security", "network security",
        "keselamatan siber", "keselamatan maklumat",
        "网络安全", "信息安全"
    ],
    "Artificial Intelligence": [
        "artificial intelligence", "machine learning", "deep learning",
        "kecerdasan buatan", "pembelajaran mesin",
        "人工智能", "机器学习", "深度学习"
    ],
    "Engineering": [
        "engineering", "general engineering",
        "kejuruteraan",
        "工程"
    ],
    "Mechanical Engineering": [
        "mechanical engineering",
        "kejuruteraan mekanikal",
        "机械工程"
    ],
    "Electrical Engineering": [
        "electrical engineering", "electronic engineering", "electronics engineering",
        "kejuruteraan elektrik", "kejuruteraan elektronik",
        "电机工程", "电子工程"
    ],
    "Civil Engineering": [
        "civil engineering",
        "kejuruteraan awam",
        "土木工程"
    ],
    "Chemical Engineering": [
        "chemical engineering",
        "kejuruteraan kimia",
        "化学工程"
    ],
    "Biomedical Engineering": [
        "biomedical engineering", "medical engineering",
        "kejuruteraan bioperubatan",
        "生物医学工程"
    ],
    "Industrial Engineering": [
        "industrial engineering",
        "kejuruteraan industri",
        "工业工程"
    ],
    "Business": [
        "business", "business studies", "business administration",
        "perniagaan", "pentadbiran perniagaan",
        "商业", "工商管理"
    ],
    "Marketing": [
        "marketing", "digital marketing", "brand management",
        "pemasaran", "pemasaran digital",
        "市场营销", "营销"
    ],
    "Finance": [
        "finance", "financial", "banking", "investment", "financial management",
        "kewangan", "perbankan", "pelaburan",
        "金融", "银行", "投资"
    ],
    "Accounting": [
        "accounting", "accountancy", "auditing",
        "perakaunan", "audit",
        "会计", "审计"
    ],
    "Economics": [
        "economics", "economic studies",
        "ekonomi",
        "经济学"
    ],
    "Human Resource Management": [
        "human resource", "human resource management", "hr management",
        "pengurusan sumber manusia", "sumber manusia",
        "人力资源", "人力资源管理"
    ],
    "Management": [
        "management", "business management", "operations management",
        "pengurusan",
        "管理学", "管理"
    ],
    "Psychology": [
        "psychology",
        "psikologi",
        "心理学"
    ],
    "Counseling": [
        "counseling", "counselling", "guidance and counseling",
        "kaunseling",
        "辅导", "咨询学"
    ],
    "Sociology": [
        "sociology",
        "sosiologi",
        "社会学"
    ],
    "Social Work": [
        "social work",
        "kerja sosial",
        "社会工作"
    ],
    "Education": [
        "education", "teaching", "pedagogy", "tesl", "early childhood education",
        "pendidikan", "pengajaran", "pendidikan awal kanak-kanak",
        "教育", "师范", "教学"
    ],
    "English": [
        "english", "english language", "english studies",
        "bahasa inggeris", "pengajian inggeris",
        "英语", "英文"
    ],
    "Chinese Studies": [
        "chinese studies", "chinese language", "mandarin studies",
        "bahasa cina", "pengajian cina",
        "中文", "华文", "汉语言"
    ],
    "Malay Studies": [
        "malay studies", "malay language", "bahasa melayu",
        "bahasa melayu", "pengajian melayu",
        "马来文", "马来研究"
    ],
    "Communication": [
        "communication", "mass communication", "media communication", "public relations",
        "komunikasi", "komunikasi massa", "perhubungan awam",
        "传播学", "大众传播", "公共关系"
    ],
    "Journalism": [
        "journalism", "media studies", "broadcasting",
        "kewartawanan", "media",
        "新闻学", "媒体研究", "广播"
    ],
    "Design": [
        "design", "graphic design", "visual communication", "multimedia design",
        "reka bentuk", "reka bentuk grafik",
        "设计", "平面设计", "视觉传达"
    ],
    "UI/UX Design": [
        "ui/ux", "ui ux", "user interface", "user experience", "interaction design",
        "reka bentuk ui/ux", "reka bentuk pengalaman pengguna",
        "ui/ux设计", "用户界面设计", "用户体验设计"
    ],
    "Multimedia": [
        "multimedia", "animation", "digital media",
        "multimedia", "animasi", "media digital",
        "多媒体", "动画", "数码媒体"
    ],
    "Architecture": [
        "architecture",
        "seni bina",
        "建筑学"
    ],
    "Law": [
        "law", "legal studies", "jurisprudence",
        "undang-undang",
        "法律", "法学"
    ],
    "Medicine": [
        "medicine", "medical studies", "doctor of medicine",
        "perubatan",
        "医学"
    ],
    "Nursing": [
        "nursing",
        "kejururawatan",
        "护理学"
    ],
    "Pharmacy": [
        "pharmacy",
        "farmasi",
        "药学"
    ],
    "Dentistry": [
        "dentistry",
        "pergigian",
        "牙医学"
    ],
    "Public Health": [
        "public health",
        "kesihatan awam",
        "公共卫生"
    ],
    "Biology": [
        "biology", "biological sciences",
        "biologi",
        "生物学"
    ],
    "Chemistry": [
        "chemistry",
        "kimia",
        "化学"
    ],
    "Physics": [
        "physics",
        "fizik",
        "物理学"
    ],
    "Mathematics": [
        "mathematics", "math", "applied mathematics",
        "matematik", "matematik gunaan",
        "数学", "应用数学"
    ],
    "Statistics": [
        "statistics", "applied statistics",
        "statistik",
        "统计学"
    ],
    "Biotechnology": [
        "biotechnology",
        "bioteknologi",
        "生物技术"
    ],
    "Environmental Science": [
        "environmental science", "environmental studies",
        "sains alam sekitar",
        "环境科学"
    ],
    "Agriculture": [
        "agriculture", "agricultural science",
        "pertanian", "sains pertanian",
        "农业", "农学"
    ],
    "Food Science": [
        "food science", "food technology",
        "sains makanan", "teknologi makanan",
        "食品科学", "食品技术"
    ],
    "Hospitality": [
        "hospitality", "hotel management",
        "hospitaliti", "pengurusan hotel",
        "酒店管理"
    ],
    "Tourism": [
        "tourism", "travel management",
        "pelancongan",
        "旅游管理", "旅游学"
    ],
    "Culinary Arts": [
        "culinary arts", "culinary", "chef training",
        "seni kulinari", "kulinari",
        "烹饪艺术", "烹饪"
    ],
    "Sports Science": [
        "sports science", "exercise science",
        "sains sukan",
        "运动科学"
    ],
    "Fashion Design": [
        "fashion design", "fashion studies",
        "reka bentuk fesyen",
        "时装设计"
    ],
    "Geography": [
        "geography",
        "geografi",
        "地理学"
    ],
    "History": [
        "history",
        "sejarah",
        "历史学"
    ],
    "Political Science": [
        "political science", "politics", "international relations",
        "sains politik", "hubungan antarabangsa",
        "政治学", "国际关系"
    ],
    "Religious Studies": [
        "religious studies", "theology", "islamic studies",
        "pengajian agama", "teologi", "pengajian islam",
        "宗教学", "神学", "伊斯兰研究"
    ],
    "Fine Arts": [
        "fine arts", "art", "visual arts",
        "seni halus", "seni visual",
        "美术", "艺术"
    ]
}

OCCUPATION_KEYWORDS = {
    "Student": ["student", "pelajar", "学生"],
    "Intern": ["intern", "internship", "trainee", "pelatih", "实习生"],
    "Software Developer": ["software developer", "developer", "programmer", "software engineer", "pembangun perisian", "软件开发"],
    "Data Analyst": ["data analyst", "analyst", "business intelligence analyst", "penganalisis data", "数据分析师"],
    "UI/UX Designer": ["ui/ux designer", "ui designer", "ux designer", "product designer", "pereka ui/ux", "设计师"],
    "Research Assistant": ["research assistant", "researcher", "pembantu penyelidik", "研究助理"],
    "Business Analyst": ["business analyst", "penganalisis perniagaan", "业务分析师"],
    "Teacher": ["teacher", "lecturer", "tutor", "instructor", "guru", "pensyarah", "教师"],
    "Freelancer": ["freelancer", "self-employed", "pekerja bebas", "自由职业者"],
    "Unemployed": ["unemployed", "between jobs", "tidak bekerja", "待业"],

    "Sales Associate": ["sales associate", "retail sales associate", "sales executive", "pegawai jualan", "销售员"],
    "Customer Service": ["customer service", "customer support", "khidmat pelanggan", "客服"],
    "Marketing Executive": ["marketing executive", "marketing specialist", "eksekutif pemasaran", "市场营销专员"],
    "Accountant": ["accountant", "bookkeeper", "akauntan", "会计师"],
    "Engineer": ["engineer", "jurutera", "工程师"],
    "Manager": ["manager", "supervisor", "pengurus", "经理"],

    "Doctor": ["doctor", "physician", "medical officer", "doktor", "医生"],
    "Nurse": ["nurse", "registered nurse", "jururawat", "护士"],
    "Pharmacist": ["pharmacist", "ahli farmasi", "药剂师"],
    "Dentist": ["dentist", "doktor gigi", "牙医"],
    "Psychologist": ["psychologist", "ahli psikologi", "心理学家"],
    "Counselor": ["counselor", "counsellor", "kaunselor", "辅导员"],
    "Social Worker": ["social worker", "pekerja sosial", "社会工作者"],

    "Lawyer": ["lawyer", "attorney", "legal counsel", "peguam", "律师"],
    "Paralegal": ["paralegal", "legal assistant", "pembantu guaman", "法律助理"],

    "Architect": ["architect", "arkitek", "建筑师"],
    "Mechanical Engineer": ["mechanical engineer", "jurutera mekanikal", "机械工程师"],
    "Electrical Engineer": ["electrical engineer", "jurutera elektrik", "电子工程师"],
    "Civil Engineer": ["civil engineer", "jurutera awam", "土木工程师"],
    "Chemical Engineer": ["chemical engineer", "jurutera kimia", "化学工程师"],

    "Graphic Designer": ["graphic designer", "pereka grafik", "平面设计师"],
    "Animator": ["animator", "animator", "动画师"],
    "Photographer": ["photographer", "jurugambar", "摄影师"],
    "Video Editor": ["video editor", "penyunting video", "视频剪辑师"],
    "Content Creator": ["content creator", "pencipta kandungan", "内容创作者"],

    "Journalist": ["journalist", "reporter", "wartawan", "记者"],
    "Writer": ["writer", "author", "copywriter", "penulis", "作家"],
    "Translator": ["translator", "interpreter", "penterjemah", "翻译员"],

    "Chef": ["chef", "cook", "cef", "主厨"],
    "Hotel Staff": ["hotel staff", "front desk", "receptionist", "petugas hotel", "酒店职员"],
    "Tour Guide": ["tour guide", "pemandu pelancong", "导游"],

    "Scientist": ["scientist", "saintis", "研究员"],
    "Lab Technician": ["lab technician", "laboratory technician", "juruteknik makmal", "实验室技术员"],

    "HR Executive": ["hr executive", "human resource executive", "eksekutif sumber manusia", "人力资源专员"],
    "Admin Assistant": ["admin assistant", "administrative assistant", "pembantu pentadbiran", "行政助理"],
    "Project Manager": ["project manager", "pengurus projek", "项目经理"],

    "Account Executive": ["account executive", "eksekutif akaun", "客户经理"],
    "Financial Analyst": ["financial analyst", "penganalisis kewangan", "金融分析师"],
    "Bank Officer": ["bank officer", "pegawai bank", "银行职员"],

    "Lecturer": ["lecturer", "pensyarah", "大学讲师"],
    "Tutor": ["tutor", "tutor", "家教"],

    "Police Officer": ["police officer", "pegawai polis", "警察"],
    "Firefighter": ["firefighter", "anggota bomba", "消防员"],
    "Military Officer": ["military officer", "pegawai tentera", "军官"]
}

SKILL_KEYWORDS = [
    # English
    "communication", "teamwork", "leadership", "problem solving", "time management",
    "analytical skills", "critical thinking", "presentation", "negotiation",
    "customer service", "adaptability", "creativity", "decision making",
    "organization", "multitasking", "attention to detail", "professionalism",
    "work ethic", "interpersonal skills",
    "microsoft office", "excel", "word", "powerpoint", "outlook", "data entry",
    "filing", "documentation", "report writing", "scheduling",
    "sales management", "revenue growth", "retail", "marketing", "business analysis",
    "accounting", "finance", "bookkeeping", "auditing", "financial reporting",
    "budgeting", "forecasting", "banking", "investment", "customer relationship management",
    "crm", "persuasive selling", "conflict resolution",
    "teaching", "lesson planning", "classroom management", "counseling",
    "research", "survey design", "data collection", "interviewing",
    "patient care", "clinical skills", "medical records", "pharmacy dispensing",
    "diagnosis", "nursing care", "first aid",
    "autocad", "solidworks", "matlab", "circuit design", "troubleshooting",
    "quality control", "manufacturing", "process improvement", "maintenance",
    "laboratory skills", "microscopy", "sample preparation", "chemical analysis",
    "biotechnology", "statistical analysis",
    "graphic design", "video editing", "photography", "animation", "illustration",
    "adobe photoshop", "adobe illustrator", "premiere pro", "after effects", "figma",
    "food preparation", "kitchen management", "hospitality service", "event planning",
    "tour guiding", "reservation handling",
    "english", "mandarin", "malay", "spanish", "french", "translation", "interpretation",
    "python", "sql", "html", "css", "javascript", "java", "c++", "c#", "php",
    "flask", "streamlit", "machine learning", "data visualization", "data visualisation",
    "database", "mysql", "postgresql", "power bi", "tableau", "web development",
    "ui/ux", "git", "github", "react", "node.js",

    # Malay
    "komunikasi", "kerja berpasukan", "kepimpinan", "penyelesaian masalah", "pengurusan masa",
    "kemahiran analitikal", "pemikiran kritis", "pembentangan", "rundingan",
    "khidmat pelanggan", "kebolehsuaian", "kreativiti", "membuat keputusan",
    "organisasi", "multitugas", "perhatian kepada perincian", "profesionalisme",
    "etika kerja", "kemahiran interpersonal",
    "microsoft office", "excel", "word", "powerpoint", "outlook", "kemasukan data",
    "pemfailan", "dokumentasi", "penulisan laporan", "penjadualan",
    "pengurusan jualan", "pertumbuhan hasil", "runcit", "pemasaran", "analisis perniagaan",
    "perakaunan", "kewangan", "pembukuan", "audit", "pelaporan kewangan",
    "belanjawan", "ramalan", "perbankan", "pelaburan", "pengurusan hubungan pelanggan",
    "jualan meyakinkan", "penyelesaian konflik",
    "pengajaran", "perancangan pelajaran", "pengurusan bilik darjah", "kaunseling",
    "penyelidikan", "reka bentuk tinjauan", "pengumpulan data", "temu bual",
    "penjagaan pesakit", "kemahiran klinikal", "rekod perubatan", "dispens farmasi",
    "diagnosis", "penjagaan kejururawatan", "pertolongan cemas",
    "autocad", "solidworks", "matlab", "reka bentuk litar", "penyelesaian masalah teknikal",
    "kawalan kualiti", "pembuatan", "penambahbaikan proses", "penyelenggaraan",
    "kemahiran makmal", "mikroskopi", "penyediaan sampel", "analisis kimia",
    "bioteknologi", "analisis statistik",
    "reka bentuk grafik", "penyuntingan video", "fotografi", "animasi", "ilustrasi",
    "adobe photoshop", "adobe illustrator", "premiere pro", "after effects", "figma",
    "penyediaan makanan", "pengurusan dapur", "perkhidmatan hospitaliti", "perancangan acara",
    "panduan pelancong", "pengendalian tempahan",
    "bahasa inggeris", "mandarin", "bahasa melayu", "spanish", "french", "terjemahan", "interpretasi",
    "python", "sql", "html", "css", "javascript", "java", "c++", "c#", "php",
    "flask", "streamlit", "pembelajaran mesin", "visualisasi data",
    "pangkalan data", "mysql", "postgresql", "power bi", "tableau", "pembangunan web",
    "ui/ux", "git", "github", "react", "node.js",

    # Mandarin
    "沟通", "团队合作", "领导力", "解决问题", "时间管理",
    "分析能力", "批判性思维", "演讲", "谈判",
    "客户服务", "适应能力", "创造力", "决策能力",
    "组织能力", "多任务处理", "注重细节", "专业素养",
    "职业道德", "人际交往能力",
    "microsoft office", "excel", "word", "powerpoint", "outlook", "数据输入",
    "归档", "文档处理", "报告写作", "排程",
    "销售管理", "营收增长", "零售", "市场营销", "商业分析",
    "会计", "金融", "簿记", "审计", "财务报告",
    "预算编制", "预测", "银行业务", "投资", "客户关系管理",
    "说服式销售", "冲突解决",
    "教学", "课程规划", "课堂管理", "辅导",
    "研究", "问卷设计", "数据收集", "访谈",
    "病人护理", "临床技能", "医疗记录", "药房配药",
    "诊断", "护理技能", "急救",
    "autocad", "solidworks", "matlab", "电路设计", "故障排除",
    "质量控制", "制造", "流程改进", "维护",
    "实验室技能", "显微镜操作", "样本制备", "化学分析",
    "生物技术", "统计分析",
    "平面设计", "视频剪辑", "摄影", "动画", "插画",
    "adobe photoshop", "adobe illustrator", "premiere pro", "after effects", "figma",
    "食品准备", "厨房管理", "酒店服务", "活动策划",
    "导游", "预订处理",
    "英语", "华语", "马来语", "西班牙语", "法语", "翻译", "口译",
    "python", "sql", "html", "css", "javascript", "java", "c++", "c#", "php",
    "flask", "streamlit", "机器学习", "数据可视化",
    "数据库", "mysql", "postgresql", "power bi", "tableau", "网页开发",
    "ui/ux", "git", "github", "react", "node.js"
]

INTEREST_KEYWORDS = [
    # English
    "technology", "web development", "data science", "machine learning", "ai",
    "business", "marketing", "sales", "finance", "accounting",
    "psychology", "education", "teaching", "research", "reading",
    "design", "photography", "animation", "art", "music",
    "travel", "tourism", "hospitality", "cooking", "baking",
    "sports", "fitness", "gym", "badminton", "football", "basketball",
    "sustainability", "environment", "blockchain", "web 3.0", "sailing",
    "volunteering", "community service", "writing", "journalism",

    # Malay
    "teknologi", "pembangunan web", "sains data", "pembelajaran mesin", "ai",
    "perniagaan", "pemasaran", "jualan", "kewangan", "perakaunan",
    "psikologi", "pendidikan", "pengajaran", "penyelidikan", "membaca",
    "reka bentuk", "fotografi", "animasi", "seni", "muzik",
    "pelancongan", "hospitaliti", "memasak", "membakar",
    "sukan", "kecergasan", "gim", "badminton", "bola sepak", "bola keranjang",
    "kelestarian", "alam sekitar", "blockchain", "web 3.0", "pelayaran",
    "sukarelawan", "khidmat masyarakat", "penulisan", "kewartawanan",

    # Mandarin
    "科技", "网页开发", "数据科学", "机器学习", "人工智能",
    "商业", "市场营销", "销售", "金融", "会计",
    "心理学", "教育", "教学", "研究", "阅读",
    "设计", "摄影", "动画", "艺术", "音乐",
    "旅游", "酒店管理", "烹饪", "烘焙",
    "运动", "健身", "羽毛球", "足球", "篮球",
    "可持续发展", "环境保护", "区块链", "web 3.0", "航海",
    "志愿服务", "社区服务", "写作", "新闻"
]


def _contains_any(text: str, keywords: List[str]) -> bool:
    lower_text = text.lower()
    return any(k.lower() in lower_text for k in keywords)


def _extract_first_match(text: str, mapping: Dict[str, List[str]]) -> str:
    lower_text = text.lower()
    for canonical, variants in mapping.items():
        for kw in variants:
            if kw.lower() in lower_text:
                return canonical
    return ""


def _extract_keywords_found(text: str, keywords: List[str]) -> List[str]:
    lower_text = text.lower()
    found: List[str] = []

    for kw in keywords:
        if kw.lower() in lower_text:
            formatted = kw.strip()
            if formatted.lower() in {"sql", "html", "css", "ui/ux", "c++", "c#"}:
                found.append(formatted.upper() if formatted.lower() in {"sql", "html", "css"} else formatted)
            else:
                found.append(formatted.title())

    # preserve order, remove duplicates
    seen = set()
    deduped = []
    for item in found:
        if item.lower() not in seen:
            seen.add(item.lower())
            deduped.append(item)

    return deduped


def _extract_latest_job_title(work_text: str) -> str:
    """
    Try to infer the latest job title from work experience section.
    """
    if not work_text:
        return ""

    lines = [ln.strip() for ln in work_text.splitlines() if ln.strip()]
    candidate_lines = []

    for ln in lines[:20]:
        if len(ln) < 3 or len(ln) > 80:
            continue
        if re.search(r"\b(20\d{2}|19\d{2})\b", ln):
            continue
        if any(sec in ln.lower() for sec in ["experience", "achievements", "work experience"]):
            continue
        candidate_lines.append(ln)

    for line in candidate_lines:
        mapped = _extract_first_match(line, OCCUPATION_KEYWORDS)
        if mapped:
            return mapped

    return ""


def _extract_career_goal_from_summary(summary_text: str) -> str:
    if not summary_text:
        return ""

    summary_text = clean_ocr_text(summary_text)
    summary_text = re.sub(r"^(summary|profile|professional summary|objective)\s*[:\-]?\s*", "", summary_text, flags=re.I)

    if len(summary_text) > 500:
        return summary_text[:500].strip()

    return summary_text.strip()


# ======================================
# Main parser
# ======================================
def parse_resume_profile(text: str) -> Dict[str, str]:
    """
    Extract basic profile information from resume text.
    Designed to be broader and less biased toward only student/tech resumes.
    """
    clean_text = clean_ocr_text(text)
    lower_text = clean_text.lower()
    sections = split_resume_sections(clean_text)

    profile: Dict[str, str] = {
        "age_range": "",
        "education_level": "",
        "field_of_study": "",
        "current_occupation": "",
        "skills": "",
        "interests": "",
        "preferred_work_style": "",
        "career_goal": ""
    }

    # ---------- Education level ----------
    education_text = sections.get("education", lower_text)
    if _contains_any(education_text, ["phd", "doctor of philosophy", "博士"]):
        profile["education_level"] = "PhD"
    elif _contains_any(education_text, ["master", "msc", "mba", "硕士", "sarjana"]):
        profile["education_level"] = "Master"
    elif _contains_any(education_text, ["bachelor", "degree", "honours", "学士", "ijazah"]):
        profile["education_level"] = "Degree"
    elif _contains_any(education_text, ["diploma", "文凭"]):
        profile["education_level"] = "Diploma"
    elif _contains_any(education_text, ["foundation", "预科", "asasi"]):
        profile["education_level"] = "Foundation"
    elif _contains_any(education_text, ["associate", "副学士"]):
        profile["education_level"] = "Diploma"

    # ---------- Field of study ----------
    field_from_education = _extract_first_match(education_text, FIELD_OF_STUDY_KEYWORDS)
    field_from_full = _extract_first_match(lower_text, FIELD_OF_STUDY_KEYWORDS)
    profile["field_of_study"] = field_from_education or field_from_full

    # ---------- Current occupation ----------
    work_text = sections.get("work_experience", "")
    occupation_from_work = _extract_latest_job_title(work_text)
    occupation_from_full = _extract_first_match(lower_text, OCCUPATION_KEYWORDS)

    # Normalize some broader mapped results back to dropdown-friendly values when possible
    normalized_occupation = occupation_from_work or occupation_from_full
    if normalized_occupation in {
        "Sales Associate", "Customer Service", "Marketing Executive",
        "Accountant", "Engineer", "Manager"
    }:
        profile["current_occupation"] = normalized_occupation
    else:
        profile["current_occupation"] = normalized_occupation

    # ---------- Skills ----------
    skills_text = sections.get("skills", clean_text)
    found_skills = _extract_keywords_found(skills_text, SKILL_KEYWORDS)

    # If skills section weak, also check full resume
    if len(found_skills) < 3:
        extra_skills = _extract_keywords_found(clean_text, SKILL_KEYWORDS)
        merged = []
        seen = set()
        for item in found_skills + extra_skills:
            if item.lower() not in seen:
                seen.add(item.lower())
                merged.append(item)
        found_skills = merged

    profile["skills"] = ", ".join(found_skills[:20])

    # ---------- Interests ----------
    interests_text = sections.get("interests", "")
    found_interests = _extract_keywords_found(interests_text, INTEREST_KEYWORDS)

    if not found_interests:
        found_interests = _extract_keywords_found(clean_text, INTEREST_KEYWORDS)

    profile["interests"] = ", ".join(found_interests[:15])

    # ---------- Preferred work style ----------
    teamwork_keywords = [
        "teamwork", "team player", "collaborate", "collaboration", "worked with a team",
        "cross-functional", "coordination", "kerja berpasukan", "团队合作"
    ]
    independent_keywords = [
        "independent", "self-learning", "self learning", "self-motivated", "work alone",
        "自主", "独立", "bekerja sendiri"
    ]
    structured_keywords = [
        "organized", "structured", "planning", "detail-oriented", "detail oriented",
        "process", "planning", "tersusun", "有条理"
    ]
    flexible_keywords = [
        "adaptable", "flexible", "fast-paced", "dynamic", "spontaneous",
        "fleksibel", "灵活"
    ]

    if _contains_any(clean_text, teamwork_keywords):
        profile["preferred_work_style"] = "Prefer teamwork"
    elif _contains_any(clean_text, independent_keywords):
        profile["preferred_work_style"] = "Prefer working alone"
    elif _contains_any(clean_text, structured_keywords):
        profile["preferred_work_style"] = "Prefer structured tasks"
    elif _contains_any(clean_text, flexible_keywords):
        profile["preferred_work_style"] = "Prefer flexible tasks"

    # ---------- Career goal ----------
    summary_text = sections.get("summary", "")
    career_goal = _extract_career_goal_from_summary(summary_text)

    if not career_goal and "objective" in lower_text:
        match = re.search(
            r"(objective|career objective|professional summary|profile)\s*[:\-]?\s*(.*?)(education|skills|experience|work experience|languages|interests|courses|certifications|$)",
            clean_text,
            flags=re.I | re.S
        )
        if match:
            career_goal = clean_ocr_text(match.group(2))[:500]

    profile["career_goal"] = career_goal.strip()

    return profile


# ======================================
# Cleanup helper
# ======================================
def cleanup_generated_resume_images(image_paths: List[str]) -> None:
    """
    Delete temporary/generated images safely.
    """
    suffixes = [
        "",
        "_processed.png",
        "_light_processed.png",
        "_left.png",
        "_right.png",
        "_left_processed.png",
        "_right_processed.png",
        "_left_light_processed.png",
        "_right_light_processed.png",
    ]

    for path in image_paths:
        try:
            base = path.rsplit(".", 1)[0]
            for suffix in suffixes:
                candidate = path if suffix == "" else base + suffix
                if os.path.exists(candidate):
                    os.remove(candidate)
        except Exception:
            pass
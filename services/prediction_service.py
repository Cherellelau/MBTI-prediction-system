import os
import re
import json

import joblib
import numpy as np
from flask import session
from deep_translator import GoogleTranslator
from db import get_user_by_id, get_user_profile_by_user_id


# ======================================
# Constants
# ======================================
ALL_MBTI_TYPES = [a + b + c + d for a in "IE" for b in "NS" for c in "TF" for d in "JP"]
VALID_MBTI_TYPES = set(ALL_MBTI_TYPES)


# ======================================
# Model loading
# ======================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "model")

vectorizer = None
models = None

def get_prediction_assets():
    global vectorizer, models

    if vectorizer is None:
        vectorizer = joblib.load(os.path.join(MODEL_DIR, "vectorizer.pkl"))

    if models is None:
        models = joblib.load(os.path.join(MODEL_DIR, "mbti_models.pkl"))

    required_keys = {"I_E", "N_S", "T_F", "J_P"}
    missing = required_keys - set(models.keys())
    if missing:
        raise KeyError(f"Missing prediction model keys: {sorted(missing)}")

    return vectorizer, models


# ======================================
# Text preprocessing
# ======================================
def clean_text_ml(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def translate_to_english(text: str, source_lang: str | None = None) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    lang_map = {
        "en": "en",
        "zh": "zh-CN",
        "ms": "ms"
    }

    src = lang_map.get((source_lang or "").lower(), "auto")

    try:
        if src == "en":
            return text
        return GoogleTranslator(source=src, target="en").translate(text)
    except Exception:
        return text

def row_to_dict(row):
    if not row:
        return {}
    return dict(row)

# ======================================
# Prediction helpers
# ======================================
def _prob_of_one(model, X, one_label=1) -> float:
    """
    Return P(y == one_label) for a binary logistic regression model.
    """
    proba = model.predict_proba(X)[0]
    classes = list(model.classes_)
    idx = classes.index(one_label)
    return float(proba[idx])


def ml_predict_top3(text: str):
    vectorizer_obj, models_obj = get_prediction_assets()

    cleaned = clean_text_ml(text)
    if not cleaned:
        return [("INTJ", 0.55), ("INFJ", 0.47), ("ISTJ", 0.39)]

    X = vectorizer_obj.transform([cleaned])

    pE = _prob_of_one(models_obj["I_E"], X, one_label=1)
    pI = 1 - pE

    pS = _prob_of_one(models_obj["N_S"], X, one_label=1)
    pN = 1 - pS

    pF = _prob_of_one(models_obj["T_F"], X, one_label=1)
    pT = 1 - pF

    pP = _prob_of_one(models_obj["J_P"], X, one_label=1)
    pJ = 1 - pP

    letter_probs = {
        "I": pI, "E": pE,
        "N": pN, "S": pS,
        "T": pT, "F": pF,
        "J": pJ, "P": pP
    }

    scores_raw = []
    for t in ALL_MBTI_TYPES:
        scores_raw.append(
            letter_probs[t[0]] *
            letter_probs[t[1]] *
            letter_probs[t[2]] *
            letter_probs[t[3]]
        )

    scores_raw = np.array(scores_raw, dtype=float)
    top_idx = scores_raw.argsort()[-3:][::-1]

    t1 = scores_raw[top_idx[0]]
    t2 = scores_raw[top_idx[1]]
    t3 = scores_raw[top_idx[2]]

    gap12 = float((t1 - t2) / (t1 + 1e-9))
    conf1 = 0.55 + 0.40 * gap12
    conf1 = float(max(0.55, min(0.95, conf1)))

    gap23 = float((t2 - t3) / (t2 + 1e-9))
    conf2 = 0.45 + 0.30 * gap23
    conf2 = float(max(0.35, min(conf1 - 0.08, conf2)))

    conf3 = float(max(0.25, conf2 - 0.10))

    top3 = [
        (ALL_MBTI_TYPES[top_idx[0]], round(conf1, 2)),
        (ALL_MBTI_TYPES[top_idx[1]], round(conf2, 2)),
        (ALL_MBTI_TYPES[top_idx[2]], round(conf3, 2)),
    ]
    return top3


# ======================================
# Session storage helpers
# ======================================
def store_pending_prediction(top3, raw_text: str = "", raw_payload: dict | None = None,
                             profile_context: dict | None = None):
    payload = {
        "top3": [{"typeCode": t, "confidence": round(float(c), 2)} for t, c in (top3 or [])]
    }

    if raw_text:
        payload["raw_text"] = raw_text.strip()

    if raw_payload is not None:
        payload["raw_payload"] = raw_payload

    if profile_context is not None:
        payload["profile_context"] = profile_context

    session["pending_pred"] = payload
    session.modified = True


def get_pending_prediction():
    return session.get("pending_pred")


def clear_pending_prediction():
    session.pop("pending_pred", None)
    session.modified = True


def get_confidence_for_type(top3, chosen: str):
    chosen = (chosen or "").strip().upper()
    for item in (top3 or []):
        if (item.get("typeCode") or "").strip().upper() == chosen:
            return item.get("confidence")
    return None


# ======================================
# Scenario / score helpers
# ======================================
def mutate_mbti_one_step(code: str) -> str:
    code = (code or "INFJ").upper().strip()
    if len(code) != 4:
        code = "INFJ"

    flip_order = [
        (0, {"E": "I", "I": "E"}),
        (1, {"S": "N", "N": "S"}),
        (2, {"T": "F", "F": "T"}),
        (3, {"J": "P", "P": "J"}),
    ]

    for idx, mapping in flip_order:
        if code[idx] in mapping:
            return code[:idx] + mapping[code[idx]] + code[idx + 1:]

    return "INFJ"


def scores_to_mbti(ei: int, sn: int, tf: int, jp: int) -> str:
    return "".join([
        "E" if ei > 0 else "I",
        "S" if sn > 0 else "N",
        "T" if tf > 0 else "F",
        "J" if jp > 0 else "P",
    ])


def confidence_from_scores(ei: int, sn: int, tf: int, jp: int) -> float:
    avg_margin = (abs(ei) / 4 + abs(sn) / 4 + abs(tf) / 4 + abs(jp) / 4) / 4
    conf = 0.55 + 0.40 * avg_margin
    return round(max(0.45, min(0.95, conf)), 2)


def score_side(pair: str, val: int) -> str:
    mapping = {
        "EI": ("E", "I"),
        "SN": ("S", "N"),
        "TF": ("T", "F"),
        "JP": ("J", "P"),
    }

    left, right = mapping[pair]
    if val > 0:
        return left
    elif val < 0:
        return right
    return "Balanced"


def option_letter_from_index(i: int) -> str:
    return ["A", "B", "C", "D"][i] if 0 <= i <= 3 else "?"


def predict_top3_from_scores(ei: int, sn: int, tf: int, jp: int):
    """
    Build 3 MBTI candidates from scenario-style dimension scores.
    """
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
    return top3


def build_pending_payload_json(top3, raw_text: str = "", raw_payload: dict | None = None) -> str:
    """
    Optional helper if you want a JSON string version for debugging/logging.
    """
    payload = {
        "top3": [{"typeCode": t, "confidence": round(float(c), 2)} for t, c in (top3 or [])]
    }

    if raw_text:
        payload["raw_text"] = raw_text.strip()

    if raw_payload is not None:
        payload["raw_payload"] = raw_payload

    return json.dumps(payload, ensure_ascii=False)

def build_profile_context_for_prediction(user_id: int) -> dict:
    user = row_to_dict(get_user_by_id(user_id))
    profile = row_to_dict(get_user_profile_by_user_id(user_id))

    return {
        "preferredLanguage": user.get("preferredLanguage", "EN"),
        "ageRange": profile.get("ageRange", ""),
        "educationLevel": profile.get("educationLevel", ""),
        "fieldOfStudy": profile.get("fieldOfStudy", ""),
        "currentOccupation": profile.get("currentOccupation", ""),
        "skills": profile.get("skills", ""),
        "interests": profile.get("interests", ""),
        "preferredWorkStyle": profile.get("preferredWorkStyle", ""),
        "careerGoal": profile.get("careerGoal", ""),
        "profileSource": profile.get("profileSource", ""),
        "profileCompleted": int(profile.get("profileCompleted", 0) or 0),
    }
    
def normalize_text(value: str) -> str:
    return (value or "").strip().lower()


def score_profile_mbti(profile_context: dict | None) -> dict:
    scores = {"EI": 0, "SN": 0, "TF": 0, "JP": 0}

    if not profile_context:
        return scores

    work_style = normalize_text(profile_context.get("preferredWorkStyle"))
    field = normalize_text(profile_context.get("fieldOfStudy"))
    occupation = normalize_text(profile_context.get("currentOccupation"))
    skills = normalize_text(profile_context.get("skills"))
    interests = normalize_text(profile_context.get("interests"))
    career_goal = normalize_text(profile_context.get("careerGoal"))
    sn_text = " ".join([field, occupation, skills, interests, career_goal])
    tf_text = " ".join([skills, interests, career_goal, occupation])

    # EI
    if any(k in work_style for k in ["alone", "independent", "independently", "solo"]):
        scores["EI"] -= 2
    if any(k in work_style for k in ["team", "teams", "collaboration", "collaborative", "group"]):
        scores["EI"] += 2

    # JP
    if any(k in work_style for k in ["structured", "organized", "organised", "planned"]) or \
       any(k in skills for k in ["organized", "organised", "planning", "planner"]):
        scores["JP"] -= 2

    if any(k in work_style for k in ["flexible", "adaptable"]) or \
       any(k in skills for k in ["adaptable"]) or \
       any(k in interests for k in ["spontaneous", "spontaneity"]):
        scores["JP"] += 2

    # SN
    if any(k in sn_text for k in ["creative", "design", "imagination", "innovative", "idea", "ideas", "concept"]):
        scores["SN"] -= 2
    if any(k in sn_text for k in ["practical", "detail", "details", "hands-on", "technical", "routine"]):
        scores["SN"] += 2

    # TF
    if any(k in tf_text for k in ["logic", "logical", "analytical", "analysis", "problem solving", "data"]):
        scores["TF"] += 2
    if any(k in tf_text for k in ["helping people", "care", "caring", "empathy", "communication", "support"]):
        scores["TF"] -= 2

    return scores

def combine_profile_with_dimension_scores(
    base_scores: dict,
    profile_scores: dict,
    profile_weight: float = 0.4
) -> dict:
    return {
        "EI": float(base_scores.get("EI", 0)) + float(profile_scores.get("EI", 0)) * profile_weight,
        "SN": float(base_scores.get("SN", 0)) + float(profile_scores.get("SN", 0)) * profile_weight,
        "TF": float(base_scores.get("TF", 0)) + float(profile_scores.get("TF", 0)) * profile_weight,
        "JP": float(base_scores.get("JP", 0)) + float(profile_scores.get("JP", 0)) * profile_weight,
    }
    
def build_profile_prompt_text(profile_context: dict | None) -> str:
    if not profile_context:
        return ""

    parts = []

    for key in [
        "ageRange",
        "educationLevel",
        "fieldOfStudy",
        "currentOccupation",
        "skills",
        "interests",
        "preferredWorkStyle",
        "careerGoal",
    ]:
        value = (profile_context.get(key) or "").strip()
        if value:
            parts.append(value)

    text = " ".join(parts).strip()
    return text[:300]

def ml_predict_top3_with_profile(text: str, profile_context: dict | None = None):
    main_text = (text or "").strip()
    profile_text = build_profile_prompt_text(profile_context)

    combined_text = f"{profile_text} {main_text}".strip() if profile_text else main_text
    return ml_predict_top3(combined_text)
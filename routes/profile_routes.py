import re
import os
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

from auth import hash_password, verify_password
from db import (
    get_user_by_id,
    get_user_profile_by_user_id,
    upsert_user_profile_manual,
    update_user_profile,
    update_user_language,
    update_user_password_hash,
    list_results_for_user,
)
from i18n import TRANSLATIONS
from werkzeug.utils import secure_filename

from services.resume_service import (
    allowed_resume_extension,
    get_file_ext,
    convert_pdf_to_images,
    extract_text_from_resume_pages,
    parse_resume_profile,
    validate_resume_image,
    validate_resume_text_only,
)

profile_bp = Blueprint("profile", __name__)


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


def get_current_user():
    return row_to_dict(get_user_by_id(session["user_id"]))


def get_user_profile(user_id: int):
    return row_to_dict(get_user_profile_by_user_id(user_id))


def user_profile_completed(user_id: int) -> bool:
    profile = get_user_profile_by_user_id(user_id)
    return bool(profile and int(profile.get("profileCompleted", 0) or 0) == 1)


def get_resume_raw_text():
    return (session.get("resume_raw_text") or "").strip()


TEXT_RE = re.compile(r"^[A-Za-z\u4e00-\u9fff0-9\s&(),.\-\/+#]+$")

VALID_AGE_RANGES = {
    "18-20", "21-25", "26-30", "31-35", "36-40", "41-45",
    "46-50", "51-55", "56-60", "61-65", "66-70", "71-75", "76-80"
}
VALID_EDUCATION_LEVELS = {"Foundation", "Diploma", "Degree", "Master", "PhD"}
VALID_WORK_STYLES = {
    "Prefer working alone",
    "Prefer teamwork",
    "Prefer structured tasks",
    "Prefer flexible tasks",
    "Hybrid",
}

OTHER_VALUES = {"Other", "Lain-lain", "其他"}

SKILL_KEYWORDS = {
    # English
    "python", "java", "c++", "c", "c#", "r", "sql", "html", "css", "javascript",
    "typescript", "php", "flask", "streamlit", "django", "react", "node.js",
    "bootstrap", "api", "database", "data structures", "algorithms",
    "machine learning", "deep learning", "artificial intelligence", "ai",
    "data analysis", "data cleaning", "data mining", "data visualization",
    "statistics", "matplotlib", "pandas", "numpy", "power bi", "tableau",
    "excel", "sas", "spark", "hadoop", "nlp", "computer vision",
    "web development", "software development", "mobile development",
    "testing", "debugging", "cybersecurity", "networking", "cloud computing",
    "analysis", "analytical", "critical thinking", "logical thinking",
    "problem solving", "troubleshooting", "research", "decision making",
    "communication", "teamwork", "leadership", "adaptability", "creativity",
    "time management", "organization", "organizing", "planning",
    "presentation", "writing", "public speaking", "collaboration",
    "interpersonal skills", "negotiation", "customer service",
    "attention to detail", "multitasking", "self learning", "independence",
    "ui design", "ux design", "graphic design", "video editing",
    "content creation", "editing", "illustration", "prototyping",
    "marketing", "business analysis", "project management", "documentation",
    "report writing", "financial analysis", "accounting", "management",

    # Malay
    "pengaturcaraan", "atur cara", "pembangunan perisian", "pembangunan web",
    "pembangunan aplikasi mudah alih", "pangkalan data", "struktur data",
    "algoritma", "pembelajaran mesin", "pembelajaran mendalam",
    "kecerdasan buatan", "analisis data", "pembersihan data", "perlombongan data",
    "visualisasi data", "statistik", "pengujian", "nyahpepijat",
    "keselamatan siber", "rangkaian", "pengkomputeran awan",
    "pemikiran analitikal", "pemikiran kritikal", "pemikiran logik",
    "penyelesaian masalah", "penyelidikan", "membuat keputusan",
    "komunikasi", "kerja berpasukan", "kepimpinan", "kebolehsuaian",
    "kreativiti", "pengurusan masa", "perancangan", "pembentangan",
    "penulisan", "kerjasama", "khidmat pelanggan", "berdikari",
    "reka bentuk ui", "reka bentuk ux", "reka bentuk grafik",
    "penyuntingan video", "penciptaan kandungan", "ilustrasi", "pemasaran",
    "analisis perniagaan", "pengurusan projek", "dokumentasi",
    "penulisan laporan", "analisis kewangan", "perakaunan", "pengurusan",

    # Mandarin
    "编程", "程序设计", "软件开发", "网页开发", "移动开发", "数据库", "数据结构",
    "算法", "机器学习", "深度学习", "人工智能", "数据分析", "数据清理",
    "数据挖掘", "数据可视化", "统计", "测试", "调试", "网络安全", "网络技术",
    "云计算", "分析能力", "批判性思维", "逻辑思维", "解决问题",
    "故障排除", "研究能力", "决策能力", "沟通能力", "团队合作", "领导力",
    "适应能力", "创造力", "时间管理", "组织能力", "规划能力", "演讲",
    "写作", "公开演讲", "合作能力", "人际交往能力", "谈判能力", "客户服务",
    "注重细节", "多任务处理", "自学能力", "独立工作",
    "界面设计", "用户体验设计", "平面设计", "视频剪辑", "内容创作",
    "编辑", "插画", "原型设计", "市场营销", "商业分析", "项目管理",
    "文档编写", "报告撰写", "财务分析", "会计", "管理"
}

INTEREST_KEYWORDS = {
    # English
    "data analysis", "data science", "programming", "coding", "software development",
    "web development", "machine learning", "artificial intelligence", "ai",
    "cybersecurity", "database", "cloud computing", "networking",
    "statistics", "mathematics", "research", "technology", "innovation",
    "psychology", "human behavior", "user research", "education",
    "counselling", "social work", "communication", "leadership",
    "business", "marketing", "finance", "economics", "entrepreneurship",
    "design", "ui ux", "graphic design", "photography", "videography",
    "video editing", "writing", "reading", "drawing", "music",
    "singing", "art", "storytelling", "content creation",
    "gaming", "sports", "fitness", "travel", "food", "cooking",
    "volunteering", "fashion", "beauty", "animals", "nature",
    "movies", "drama", "anime", "books", "blogging",

    # Malay
    "analisis data", "sains data", "pengaturcaraan", "pembangunan perisian",
    "pembangunan web", "pembelajaran mesin", "kecerdasan buatan",
    "keselamatan siber", "pangkalan data", "pengkomputeran awan", "rangkaian",
    "statistik", "matematik", "penyelidikan", "teknologi", "inovasi",
    "psikologi", "tingkah laku manusia", "penyelidikan pengguna", "pendidikan",
    "kaunseling", "kerja sosial", "komunikasi", "kepimpinan",
    "perniagaan", "pemasaran", "kewangan", "ekonomi", "keusahawanan",
    "reka bentuk", "reka bentuk grafik", "fotografi", "videografi",
    "penyuntingan video", "penulisan", "membaca", "melukis", "muzik",
    "menyanyi", "seni", "penceritaan", "penciptaan kandungan",
    "permainan", "sukan", "kecergasan", "pelancongan", "makanan", "memasak",
    "sukarelawan", "fesyen", "kecantikan", "haiwan", "alam semula jadi",
    "filem", "drama", "anime", "buku", "blog",

    # Mandarin
    "数据分析", "数据科学", "编程", "软件开发", "网页开发", "机器学习",
    "人工智能", "网络安全", "数据库", "云计算", "网络技术",
    "统计", "数学", "研究", "科技", "创新",
    "心理学", "人类行为", "用户研究", "教育", "辅导", "社会工作",
    "沟通", "领导力", "商业", "市场营销", "金融", "经济", "创业",
    "设计", "平面设计", "摄影", "摄像", "视频剪辑", "写作", "阅读",
    "绘画", "音乐", "唱歌", "艺术", "讲故事", "内容创作",
    "游戏", "运动", "健身", "旅游", "美食", "烹饪", "志愿服务",
    "时尚", "美容", "动物", "大自然", "电影", "电视剧", "动漫", "书籍", "博客"
}

CAREER_KEYWORDS = {
    # English
    "career", "goal", "future", "become", "work as", "work in", "pursue",
    "develop", "improve", "build", "gain", "learn", "grow", "achieve",
    "professional", "experience", "skills", "knowledge", "expertise",
    "data analyst", "data scientist", "data engineer", "software engineer",
    "software developer", "web developer", "full stack developer",
    "backend developer", "frontend developer", "mobile app developer",
    "machine learning engineer", "ai engineer", "cybersecurity analyst",
    "network engineer", "system analyst", "business analyst", "ui designer",
    "ux designer", "ux researcher", "product designer", "qa engineer",
    "manager", "project manager", "marketing executive", "accountant",
    "financial analyst", "consultant", "entrepreneur", "administrator",
    "hr executive", "sales executive",
    "teacher", "lecturer", "researcher", "counsellor", "psychologist",
    "trainer", "educator", "social worker",
    "internship", "industry experience", "real-world experience",
    "practical skills", "career growth", "long-term career", "job opportunity",

    # Malay
    "kerjaya", "matlamat", "masa depan", "menjadi", "bekerja sebagai",
    "bekerja dalam", "menceburi", "membangunkan", "meningkatkan",
    "membina", "memperoleh", "belajar", "berkembang", "mencapai",
    "profesional", "pengalaman", "kemahiran", "pengetahuan", "kepakaran",
    "penganalisis data", "saintis data", "jurutera data", "jurutera perisian",
    "pembangun perisian", "pembangun web", "pembangun full stack",
    "pembangun backend", "pembangun frontend", "pembangun aplikasi mudah alih",
    "jurutera pembelajaran mesin", "jurutera ai", "penganalisis keselamatan siber",
    "jurutera rangkaian", "penganalisis sistem", "penganalisis perniagaan",
    "pereka ui", "pereka ux", "penyelidik ux", "pereka produk", "jurutera qa",
    "pengurus", "pengurus projek", "eksekutif pemasaran", "akauntan",
    "penganalisis kewangan", "perunding", "usahawan", "pentadbir",
    "eksekutif hr", "eksekutif jualan",
    "guru", "pensyarah", "penyelidik", "kaunselor", "ahli psikologi",
    "jurulatih", "pendidik", "pekerja sosial",
    "latihan industri", "pengalaman industri", "pengalaman dunia sebenar",
    "kemahiran praktikal", "perkembangan kerjaya", "kerjaya jangka panjang",
    "peluang pekerjaan",

    # Mandarin
    "职业", "事业", "目标", "未来", "成为", "从事", "发展", "提升", "建立",
    "获得", "学习", "成长", "实现", "专业", "经验", "技能", "知识", "专长",
    "数据分析师", "数据科学家", "数据工程师", "软件工程师", "软件开发员",
    "网页开发员", "全栈开发员", "后端开发员", "前端开发员", "移动应用开发员",
    "机器学习工程师", "人工智能工程师", "网络安全分析师", "网络工程师",
    "系统分析师", "商业分析师", "界面设计师", "用户体验设计师",
    "用户研究员", "产品设计师", "测试工程师",
    "经理", "项目经理", "市场营销执行员", "会计", "财务分析师", "顾问",
    "企业家", "行政人员", "人力资源执行员", "销售执行员",
    "教师", "讲师", "研究员", "辅导员", "心理学家", "培训师", "教育工作者", "社工",
    "实习", "行业经验", "实际经验", "实践技能", "职业发展", "长期职业", "工作机会"
}

OCCUPATION_KEYWORDS = {
    # English
    "student", "intern", "software developer", "data analyst", "ui/ux designer",
    "research assistant", "business analyst", "teacher", "freelancer", "unemployed",
    "software engineer", "web developer", "frontend developer", "backend developer",
    "full stack developer", "mobile app developer", "programmer", "coder",
    "system analyst", "data scientist", "data engineer", "machine learning engineer",
    "ai engineer", "qa engineer", "test engineer", "it support", "network engineer",
    "cybersecurity analyst", "database administrator", "cloud engineer",
    "graphic designer", "product designer", "ux researcher", "content creator",
    "video editor", "photographer", "multimedia designer", "illustrator",
    "marketing executive", "sales executive", "account assistant", "accountant",
    "financial analyst", "hr executive", "human resource executive", "administrator",
    "admin assistant", "project coordinator", "project manager", "operations executive",
    "customer service", "customer service executive", "consultant", "manager",
    "lecturer", "tutor", "trainer", "educator", "researcher", "lab assistant",
    "teaching assistant", "counsellor", "therapist", "psychologist", "social worker",
    "part time worker", "part-time worker", "self employed", "self-employed",
    "entrepreneur", "business owner", "clerk", "office assistant", "assistant",

    # Malay
    "pelajar", "intern", "pelatih industri", "pembangun perisian",
    "penganalisis data", "pereka ui/ux", "pembantu penyelidik", "penganalisis perniagaan",
    "guru", "freelancer", "penganggur", "jurutera perisian", "pembangun web",
    "pembangun frontend", "pembangun backend", "pembangun full stack",
    "pembangun aplikasi mudah alih", "pengatur cara", "programmer",
    "penganalisis sistem", "saintis data", "jurutera data",
    "jurutera pembelajaran mesin", "jurutera ai", "jurutera qa",
    "jurutera ujian", "sokongan it", "jurutera rangkaian",
    "penganalisis keselamatan siber", "pentadbir pangkalan data", "jurutera awan",
    "pereka grafik", "pereka produk", "penyelidik ux", "pencipta kandungan",
    "penyunting video", "jurugambar", "pereka multimedia", "ilustrator",
    "eksekutif pemasaran", "eksekutif jualan", "pembantu akaun", "akauntan",
    "penganalisis kewangan", "eksekutif hr", "pentadbir", "pembantu pentadbiran",
    "penyelaras projek", "pengurus projek", "eksekutif operasi",
    "khidmat pelanggan", "eksekutif khidmat pelanggan", "perunding", "pengurus",
    "pensyarah", "tutor", "jurulatih", "pendidik", "penyelidik",
    "pembantu makmal", "pembantu pengajar", "kaunselor", "terapis",
    "ahli psikologi", "pekerja sosial", "pekerja sambilan",
    "bekerja sendiri", "usahawan", "pemilik perniagaan", "kerani",
    "pembantu pejabat", "pembantu",

    # Mandarin
    "学生", "实习生", "软件开发员", "数据分析师", "界面/用户体验设计师",
    "研究助理", "商业分析师", "教师", "自由职业者", "待业",
    "软件工程师", "网页开发员", "前端开发员", "后端开发员", "全栈开发员",
    "移动应用开发员", "程序员", "系统分析师", "数据科学家", "数据工程师",
    "机器学习工程师", "人工智能工程师", "测试工程师", "it支持",
    "网络工程师", "网络安全分析师", "数据库管理员", "云工程师",
    "平面设计师", "产品设计师", "用户研究员", "内容创作者",
    "视频剪辑师", "摄影师", "多媒体设计师", "插画师",
    "市场营销执行员", "销售执行员", "会计助理", "会计", "财务分析师",
    "人力资源执行员", "行政人员", "行政助理", "项目协调员", "项目经理",
    "运营执行员", "客户服务", "客户服务执行员", "顾问", "经理",
    "讲师", "导师", "培训师", "教育工作者", "研究员", "实验室助理",
    "助教", "辅导员", "治疗师", "心理学家", "社工",
    "兼职人员", "自由工作者", "自雇人士", "企业家", "公司老板",
    "文员", "办公室助理", "助理"
}


def is_valid_text(value: str, min_len: int = 2, max_len: int = 100) -> bool:
    value = (value or "").strip()
    if not (min_len <= len(value) <= max_len):
        return False
    return bool(TEXT_RE.fullmatch(value))


def normalize_free_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def has_letters(value: str) -> bool:
    return bool(re.search(r"[A-Za-z\u4e00-\u9fff]", value or ""))


def looks_like_gibberish(value: str) -> bool:
    value = normalize_free_text(value)
    if not value:
        return True

    if re.fullmatch(r"(.)\1{4,}", value):
        return True

    if re.fullmatch(r"([A-Za-z]{2,4})\1{2,}", value):
        return True

    if len(re.findall(r"[^A-Za-z\u4e00-\u9fff0-9\s,./&()+#\-]", value)) > 3:
        return True

    return False


def contains_any_keyword(value: str, keywords: set[str]) -> bool:
    value = normalize_free_text(value).replace("-", " ")
    for keyword in keywords:
        k = normalize_free_text(keyword).replace("-", " ")
        if k and k in value:
            return True
    return False


def is_meaningful_textarea(value: str, min_len: int = 3, max_len: int = 500) -> bool:
    value = (value or "").strip()
    if not (min_len <= len(value) <= max_len):
        return False
    if not has_letters(value):
        return False
    if looks_like_gibberish(value):
        return False
    return True


def validate_skills_text(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return True
    if not is_meaningful_textarea(value, 2, 500):
        return False
    return contains_any_keyword(value, SKILL_KEYWORDS)


def validate_interests_text(value: str) -> bool:
    value = (value or "").strip()
    if not is_meaningful_textarea(value, 3, 500):
        return False
    return contains_any_keyword(value, INTEREST_KEYWORDS)


def validate_career_goal_text(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return True
    if not is_meaningful_textarea(value, 6, 500):
        return False
    return contains_any_keyword(value, CAREER_KEYWORDS)


def validate_current_occupation_text(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return True
    if not is_valid_text(value, 2, 100):
        return False
    if looks_like_gibberish(value):
        return False
    return contains_any_keyword(value, OCCUPATION_KEYWORDS)


def validate_profile_form(
    age_range: str,
    education_level: str,
    field_of_study: str,
    current_occupation: str,
    skills: str,
    interests: str,
    preferred_work_style: str,
    career_goal: str,
):
    errors = []
    invalid_fields = set()

    if age_range not in VALID_AGE_RANGES:
        errors.append(t_py("profile_err_age_range"))
        invalid_fields.add("age_range")

    if education_level not in VALID_EDUCATION_LEVELS:
        errors.append(t_py("profile_err_education_level"))
        invalid_fields.add("education_level")

    if not is_valid_text(field_of_study, 2, 100):
        errors.append(t_py("profile_err_field_of_study"))
        invalid_fields.add("field_of_study")

    if not validate_current_occupation_text(current_occupation):
        errors.append(t_py("profile_err_current_occupation"))
        invalid_fields.add("current_occupation")

    if not validate_skills_text(skills):
        errors.append(t_py("profile_err_skills"))
        invalid_fields.add("skills")

    if not validate_interests_text(interests):
        errors.append(t_py("profile_err_interests"))
        invalid_fields.add("interests")

    if preferred_work_style not in VALID_WORK_STYLES:
        errors.append(t_py("profile_err_work_style"))
        invalid_fields.add("preferred_work_style")

    if not validate_career_goal_text(career_goal):
        errors.append(t_py("profile_err_career_goal"))
        invalid_fields.add("career_goal")

    return errors, invalid_fields


def get_profile_form_data(form):
    age_range = (form.get("age_range") or "").strip()
    education_level = (form.get("education_level") or "").strip()

    field_of_study = (form.get("field_of_study") or "").strip()
    field_of_study_other = (form.get("field_of_study_other") or "").strip()

    current_occupation = (form.get("current_occupation") or "").strip()
    current_occupation_other = (form.get("current_occupation_other") or "").strip()

    skills = (form.get("skills") or "").strip()
    interests = (form.get("interests") or "").strip()
    preferred_work_style = (form.get("preferred_work_style") or "").strip()
    career_goal = (form.get("career_goal") or "").strip()

    if field_of_study in OTHER_VALUES:
        field_of_study = field_of_study_other

    if current_occupation in OTHER_VALUES:
        current_occupation = current_occupation_other

    return {
        "age_range": age_range,
        "education_level": education_level,
        "field_of_study": field_of_study,
        "field_of_study_other": field_of_study_other,
        "current_occupation": current_occupation,
        "current_occupation_other": current_occupation_other,
        "skills": skills,
        "interests": interests,
        "preferred_work_style": preferred_work_style,
        "career_goal": career_goal,
    }


def validate_profile_form_data(form_data: dict):
    return validate_profile_form(
        age_range=form_data["age_range"],
        education_level=form_data["education_level"],
        field_of_study=form_data["field_of_study"],
        current_occupation=form_data["current_occupation"],
        skills=form_data["skills"],
        interests=form_data["interests"],
        preferred_work_style=form_data["preferred_work_style"],
        career_goal=form_data["career_goal"],
    )


def build_profile_form_data_for_render(form_data, invalid_fields):
    return {
        "age_range": "" if "age_range" in invalid_fields else form_data["age_range"],
        "education_level": "" if "education_level" in invalid_fields else form_data["education_level"],
        "field_of_study": "" if "field_of_study" in invalid_fields else form_data["field_of_study"],
        "field_of_study_other": "" if "field_of_study" in invalid_fields else form_data["field_of_study_other"],
        "current_occupation": "" if "current_occupation" in invalid_fields else form_data["current_occupation"],
        "current_occupation_other": "" if "current_occupation" in invalid_fields else form_data["current_occupation_other"],
        "skills": "" if "skills" in invalid_fields else form_data["skills"],
        "interests": "" if "interests" in invalid_fields else form_data["interests"],
        "preferred_work_style": "" if "preferred_work_style" in invalid_fields else form_data["preferred_work_style"],
        "career_goal": "" if "career_goal" in invalid_fields else form_data["career_goal"],
    }


def save_profile(user_id: int, form_data: dict, profile_source: str):
    upsert_user_profile_manual(
        user_id=user_id,
        age_range=form_data["age_range"],
        education_level=form_data["education_level"],
        field_of_study=form_data["field_of_study"],
        current_occupation=form_data["current_occupation"],
        skills=form_data["skills"],
        interests=form_data["interests"],
        preferred_work_style=form_data["preferred_work_style"],
        career_goal=form_data["career_goal"],
        profile_source=profile_source,
        profile_completed=1,
    )


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ======================================
# Home
# ======================================
@profile_bp.get("/home")
@login_required
def home_page():
    user = get_current_user()
    name = (user.get("name") or session.get("name") or "").strip() if user else (session.get("name") or "")

    latest = None
    try:
        results = list_results_for_user(session["user_id"])
        if results:
            latest = dict(results[0])
    except Exception as e:
        print("HOME latest error:", e)

    return render_template("home.html", name=name, latest=latest)


# ======================================
# Onboarding / Manual Profile
# ======================================
@profile_bp.get("/profile/onboarding")
@login_required
def profile_onboarding():
    if user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.home_page"))
    return render_template("profile_onboarding.html")


@profile_bp.get("/profile/manual")
@login_required
def profile_manual():
    user_id = session["user_id"]

    if user_profile_completed(user_id):
        return redirect(url_for("profile.home_page"))

    profile = get_user_profile(user_id)
    return render_template("profile_manual.html", profile=profile)


@profile_bp.post("/profile/manual")
@login_required
def profile_manual_post():
    user_id = session["user_id"]
    form_data = get_profile_form_data(request.form)

    errors, invalid_fields = validate_profile_form_data(form_data)

    if errors:
        return render_template(
            "profile_manual.html",
            profile=build_profile_form_data_for_render(form_data, invalid_fields),
            invalid_fields=list(invalid_fields),
        )

    save_profile(user_id, form_data, profile_source="manual")
    flash(t_py("msg_profile_completed_success"), "success")
    return redirect(url_for("profile.home_page"))


# ======================================
# Resume Upload / OCR / Confirm
# ======================================
@profile_bp.get("/profile/upload-resume")
@login_required
def upload_resume_page():
    if user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.home_page"))

    session["resume_entry_mode"] = "upload"
    return render_template("upload_resume.html")


@profile_bp.post("/profile/upload-resume")
@login_required
def upload_resume_post():
    file = request.files.get("resume")

    if not file or file.filename == "":
        flash(t_py("resume_upload_missing"), "error")
        return redirect(url_for("profile.upload_resume_page"))

    filename = secure_filename(file.filename)
    if not allowed_resume_extension(filename):
        flash(t_py("resume_upload_invalid_type"), "error")
        return redirect(url_for("profile.upload_resume_page"))

    ext = get_file_ext(filename)

    save_dir = os.path.join(BASE_DIR, "uploads", "resumes")
    os.makedirs(save_dir, exist_ok=True)

    save_path = os.path.join(save_dir, filename)
    file.save(save_path)

    image_paths = []

    try:
        if ext in [".png", ".jpg", ".jpeg", ".webp"]:
            image_paths = [save_path]
        elif ext == ".pdf":
            image_paths = convert_pdf_to_images(save_path)
        else:
            flash(t_py("resume_upload_invalid_type"), "error")
            return redirect(url_for("profile.upload_resume_page"))

        raw_text = extract_text_from_resume_pages(image_paths)
        validation = validate_resume_text_only(raw_text)

        if not validation["valid"]:
            error_key = validation.get("error_key", "")

            if os.path.exists(save_path):
                os.remove(save_path)

            for path in image_paths:
                try:
                    if os.path.exists(path) and path != save_path:
                        os.remove(path)

                    for suffix in [
                        "_processed.png",
                        "_light_processed.png",
                        "_left.png",
                        "_right.png",
                        "_left_processed.png",
                        "_right_processed.png",
                        "_left_light_processed.png",
                        "_right_light_processed.png",
                    ]:
                        candidate = path.rsplit(".", 1)[0] + suffix
                        if os.path.exists(candidate):
                            os.remove(candidate)
                except Exception:
                    pass

            if error_key == "resume_not_relevant":
                flash(t_py("msg_resume_not_relevant_upload"), "error")
            elif error_key == "resume_capture_quality_error":
                flash(t_py("msg_resume_capture_quality_error"), "error")
            else:
                flash(t_py("resume_upload_ocr_empty"), "error")

            return redirect(url_for("profile.upload_resume_page"))

        session["resume_raw_text"] = raw_text
        session["resume_profile_source"] = "resume"
        session["resume_entry_mode"] = "upload"
        return redirect(url_for("profile.preview_resume_text"))

    except Exception as e:
        flash(f"OCR failed: {e}", "error")
        return redirect(url_for("profile.upload_resume_page"))

@profile_bp.get("/profile/preview-resume-text")
@login_required
def preview_resume_text():
    if user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.home_page"))

    raw_text = get_resume_raw_text()
    if not raw_text:
        flash(t_py("resume_upload_ocr_empty"), "error")
        return redirect(url_for("profile.upload_resume_page"))

    return render_template("preview_resume_text.html", raw_text=raw_text)


@profile_bp.get("/profile/parse-resume")
@login_required
def parse_resume_profile_page():
    if user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.home_page"))

    raw_text = get_resume_raw_text()
    if not raw_text:
        flash(t_py("resume_upload_ocr_empty"), "error")
        return redirect(url_for("profile.upload_resume_page"))

    extracted_profile = parse_resume_profile(raw_text)
    session["resume_profile_draft"] = extracted_profile

    source = session.get("resume_profile_source", "resume")
    return render_template("confirm_profile.html", profile=extracted_profile, source=source)


@profile_bp.post("/profile/confirm-resume")
@login_required
def confirm_resume_profile_post():
    user_id = session["user_id"]
    form_data = get_profile_form_data(request.form)

    errors, invalid_fields = validate_profile_form_data(form_data)

    if errors:
        source = session.get("resume_profile_source", "resume")
        return render_template(
            "confirm_profile.html",
            profile=build_profile_form_data_for_render(form_data, invalid_fields),
            source=source,
            invalid_fields=list(invalid_fields),
        )

    save_profile(
        user_id,
        form_data,
        profile_source=session.get("resume_profile_source", "resume"),
    )

    session.pop("resume_profile_draft", None)
    session.pop("resume_raw_text", None)
    session.pop("resume_profile_source", None)

    flash(t_py("msg_profile_saved_success"), "success")
    return redirect(url_for("profile.home_page"))


# ======================================
# Profile Page / Update / Password
# ======================================
@profile_bp.get("/profile")
@login_required
def profile():
    user = get_current_user()
    user_profile = get_user_profile(session["user_id"])
    current_lang = session.get("lang", "EN")

    return render_template(
        "profile.html",
        user=user,
        user_profile=user_profile,
        current_lang=current_lang,
    )


@profile_bp.post("/profile/update")
@login_required
def profile_update():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    preferred_language = request.form.get(
        "preferred_language",
        session.get("lang", "EN")
    ).strip().upper()

    if not email:
        flash(t_py("msg_email_empty"), "error")
        return redirect(url_for("profile.profile"))

    try:
        update_user_profile(session["user_id"], name, email)
        update_user_language(session["user_id"], preferred_language)

        session["name"] = name
        session["email"] = email
        session["lang"] = preferred_language

        flash(t_py("msg_profile_updated"), "success")
    except Exception as e:
        flash(t_py("msg_profile_update_failed").format(error=str(e)), "error")

    return redirect(request.referrer or url_for("profile.profile"))


@profile_bp.post("/profile/password")
@login_required
def profile_change_password():
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not new_pw or len(new_pw) < 6:
        flash(t_py("msg_pw_too_short"), "error")
        return redirect(url_for("profile.profile"))

    if new_pw != confirm_pw:
        flash(t_py("msg_pw_not_match"), "error")
        return redirect(url_for("profile.profile"))

    user = get_current_user()

    if not user:
        session.clear()
        flash(t_py("msg_session_expired"), "warning")
        return redirect(url_for("auth.login"))

    if not verify_password(current_pw, user["passwordHash"]):
        flash(t_py("msg_current_pw_wrong"), "error")
        return redirect(url_for("profile.profile"))

    try:
        update_user_password_hash(session["user_id"], hash_password(new_pw))
        flash(t_py("msg_password_changed"), "success")
    except Exception as e:
        flash(t_py("msg_change_pw_failed").format(error=str(e)), "error")

    return redirect(url_for("profile.profile"))


@profile_bp.get("/profile/capture-resume")
@login_required
def capture_resume_page():
    if user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.home_page"))

    session["resume_entry_mode"] = "camera"

    fresh = request.args.get("fresh") == "1"
    if fresh:
        session.pop("resume_captured_image", None)

    captured_image = session.get("resume_captured_image")
    return render_template("capture_resume.html", captured_image=captured_image)


@profile_bp.post("/profile/capture-resume")
@login_required
def capture_resume_post():
    if user_profile_completed(session["user_id"]):
        return redirect(url_for("profile.home_page"))

    file = request.files.get("resume_photo")

    if not file or file.filename == "":
        flash(t_py("msg_resume_photo_required"), "error")
        return redirect(url_for("profile.capture_resume_page", fresh=1))

    try:
        import uuid

        save_dir = os.path.join(BASE_DIR, "static", "uploads", "resumes")
        os.makedirs(save_dir, exist_ok=True)

        original_name = secure_filename(file.filename)
        ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "jpg"

        allowed_ext = {"jpg", "jpeg", "png", "webp"}
        if ext not in allowed_ext:
            flash(t_py("msg_resume_invalid_format"), "error")
            return redirect(url_for("profile.capture_resume_page", fresh=1))

        filename = f"camera_resume_{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(save_dir, filename)

        file.save(save_path)

        validation = validate_resume_image(save_path, lang="eng")

        if not validation["valid"]:
            error_key = validation.get("error_key", "")

            if os.path.exists(save_path):
                os.remove(save_path)

            for suffix in [
                "_processed.png",
                "_light_processed.png",
                "_left.png",
                "_right.png",
                "_left_processed.png",
                "_right_processed.png",
                "_left_light_processed.png",
                "_right_light_processed.png",
            ]:
                candidate = save_path.rsplit(".", 1)[0] + suffix
                if os.path.exists(candidate):
                    os.remove(candidate)

            if error_key == "resume_not_relevant":
                flash(t_py("msg_resume_not_relevant"), "error")
            else:
                flash(t_py("msg_resume_capture_quality_error"), "error")

            return redirect(url_for("profile.capture_resume_page", fresh=1))

        raw_text = validation["raw_text"]

        session["resume_raw_text"] = raw_text
        session["resume_profile_source"] = "camera"
        session["resume_entry_mode"] = "camera"
        session["resume_captured_image"] = filename

        return redirect(url_for("profile.preview_resume_text"))

    except Exception as e:
        print("Capture OCR failed:", e)
        flash(t_py("msg_resume_capture_quality_error"), "error")
        return redirect(url_for("profile.capture_resume_page", fresh=1))
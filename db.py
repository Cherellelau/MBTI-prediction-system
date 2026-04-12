import sqlite3
import os
from datetime import datetime
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(__file__), "mbti.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_user_is_admin(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(User)")
    cols = [row["name"] for row in cur.fetchall()]
    if "isAdmin" not in cols:
        cur.execute("ALTER TABLE User ADD COLUMN isAdmin INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        
def upsert_scenario_question(groupID: int, language: str, category: str, scenarioText: str):
    conn = get_conn()
    cur = conn.cursor()
    language = (language or "EN").upper()

    cur.execute("""
        UPDATE Scenario_Question
        SET category = ?, scenarioText = ?
        WHERE groupID = ? AND language = ?
    """, (category, scenarioText, int(groupID), language))

    if cur.rowcount == 0:
        cur.execute("""
            INSERT INTO Scenario_Question (groupID, language, category, scenarioText)
            VALUES (?, ?, ?, ?)
        """, (int(groupID), language, category, scenarioText))

    conn.commit()
    conn.close()

def delete_scenario_question_group(groupID: int):
    conn = get_conn()
    cur = conn.cursor()

    # get all questionIDs in this group
    cur.execute("SELECT questionID FROM Scenario_Question WHERE groupID = ?", (int(groupID),))
    qids = [int(r["questionID"]) for r in cur.fetchall()]

    # delete options first
    if qids:
        cur.executemany("DELETE FROM Scenario_Option WHERE questionID = ?", [(qid,) for qid in qids])

    # delete questions (all languages)
    cur.execute("DELETE FROM Scenario_Question WHERE groupID = ?", (int(groupID),))

    conn.commit()
    conn.close()

def next_question_group_id() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(groupID), 0) + 1 AS nextGid FROM Scenario_Question")
    gid = int(cur.fetchone()["nextGid"])
    conn.close()
    return gid

def list_scenario_questions(lang: str = "EN"):
    conn = get_conn()
    cur = conn.cursor()
    lang = (lang or "EN").upper()
    if lang not in ("EN", "ZH", "BM"):
        lang = "EN"

    cur.execute("""
        SELECT questionID, groupID, category, scenarioText, language
        FROM Scenario_Question
        WHERE language = ?
          AND groupID IS NOT NULL
        ORDER BY groupID ASC
    """, (lang,))
    rows = cur.fetchall()
    conn.close()
    return rows

def admin_create_question(language: str, category: str, scenario_text: str) -> int:
    language = (language or "EN").strip().upper()
    if language not in ("EN", "ZH", "BM"):
        language = "EN"

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO Scenario_Question (language, category, scenarioText, groupID)
            VALUES (?, ?, ?, NULL)
        """, (language, category, scenario_text))
        qid = cur.lastrowid

        # ✅ make itself the root group if groupID not set
        cur.execute("""
            UPDATE Scenario_Question
            SET groupID = ?
            WHERE questionID = ?
        """, (qid, qid))

        conn.commit()
        return qid


def admin_create_default_options(question_id: int):
    keys = ["A", "B", "C", "D"]
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executemany("""
            INSERT INTO Scenario_Option (questionID, optionKey, optionText, EIScore, SNScore, TFScore, JPScore)
            VALUES (?, ?, ?, 0, 0, 0, 0)
        """, [(question_id, k, "") for k in keys])
        conn.commit()

def admin_get_question(question_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM Scenario_Question WHERE questionID = ?", (question_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def admin_get_options(question_id: int):
    conn = get_conn()
    cur = conn.execute("""
        SELECT optionID, questionID, optionKey, optionText,
               EIScore, SNScore, TFScore, JPScore
        FROM Scenario_Option
        WHERE questionID = ?
        ORDER BY optionKey ASC
    """, (question_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def admin_update_question(question_id: int, language: str, category: str, scenario_text: str):
    language = (language or "EN").strip().upper()
    if language not in ("EN", "ZH", "BM"):
        language = "EN"

    with get_conn() as conn:
        conn.execute("""
            UPDATE Scenario_Question
            SET language = ?, category = ?, scenarioText = ?
            WHERE questionID = ?
        """, (language, category, scenario_text, question_id))
        conn.commit()


def admin_create_option(question_id: int, option_key: str, option_text: str,
                        ei: int, sn: int, tf: int, jp: int) -> int:
    option_key = (option_key or "").strip().upper()
    if option_key not in ("A", "B", "C", "D"):
        option_key = "A"

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO Scenario_Option
            (questionID, optionKey, optionText, EIScore, SNScore, TFScore, JPScore)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (int(question_id), option_key, option_text.strip(),
              int(ei), int(sn), int(tf), int(jp)))
        conn.commit()
        return cur.lastrowid

def admin_update_option(option_id: int, option_key: str, option_text: str,
                        ei: int, sn: int, tf: int, jp: int):
    option_key = (option_key or "").strip().upper()
    if option_key not in ("A", "B", "C", "D"):
        option_key = "A"

    with get_conn() as conn:
        conn.execute("""
            UPDATE Scenario_Option
            SET optionKey = ?, optionText = ?,
                EIScore = ?, SNScore = ?, TFScore = ?, JPScore = ?
            WHERE optionID = ?
        """, (option_key, option_text.strip(),
              int(ei), int(sn), int(tf), int(jp),
              int(option_id)))
        conn.commit()

def admin_delete_option(option_id: int):
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT optionID, questionID, optionKey
            FROM Scenario_Option
            WHERE optionID = ?
        """, (int(option_id),))
        opt = cur.fetchone()
        if not opt:
            return

        qid = int(opt["questionID"])
        key = (opt["optionKey"] or "").strip().upper()

        cur.execute("""
            SELECT questionID, groupID, category, language
            FROM Scenario_Question
            WHERE questionID = ?
        """, (qid,))
        qrow = cur.fetchone()
        if not qrow:
            cur.execute("DELETE FROM Scenario_Option WHERE optionID = ?", (int(option_id),))
            conn.commit()
            return

        group_id = int(qrow["groupID"] or qid)
        category = (qrow["category"] or "").strip()
        lang_now = (qrow["language"] or "EN").upper()

        def get_ids(lang: str):
            cur.execute("""
                SELECT questionID
                FROM Scenario_Question
                WHERE language = ? AND category = ?
                ORDER BY questionID ASC
            """, (lang, category))
            return [int(x["questionID"]) for x in cur.fetchall()]

        en_ids = get_ids("EN")
        bm_ids = get_ids("BM")
        zh_ids = get_ids("ZH")

        idx = None
        if group_id in en_ids:
            idx = en_ids.index(group_id)
        elif lang_now == "EN" and qid in en_ids:
            idx = en_ids.index(qid)
        elif lang_now == "BM" and qid in bm_ids:
            idx = bm_ids.index(qid)
        elif lang_now == "ZH" and qid in zh_ids:
            idx = zh_ids.index(qid)

        target_qids = set()

        # group-linked questions
        cur.execute("SELECT questionID FROM Scenario_Question WHERE groupID = ?", (group_id,))
        for r in cur.fetchall():
            target_qids.add(int(r["questionID"]))

        # fallback slot
        if idx is not None:
            if idx < len(en_ids): target_qids.add(en_ids[idx])
            if idx < len(bm_ids): target_qids.add(bm_ids[idx])
            if idx < len(zh_ids): target_qids.add(zh_ids[idx])

        # --- Delete by optionKey if possible ---
        deleted_any = False
        if key and target_qids:
            cur.executemany(
                "DELETE FROM Scenario_Option WHERE questionID = ? AND optionKey = ?",
                [(x, key) for x in target_qids]
            )
            deleted_any = True

        # --- Fallback delete by option index ---
        if not deleted_any:
            cur.execute("""
                SELECT optionID
                FROM Scenario_Option
                WHERE questionID = ?
                ORDER BY optionID ASC
            """, (qid,))
            base_oids = [int(r["optionID"]) for r in cur.fetchall()]
            if int(option_id) in base_oids:
                opt_idx = base_oids.index(int(option_id))

                for tq in target_qids:
                    cur.execute("""
                        SELECT optionID
                        FROM Scenario_Option
                        WHERE questionID = ?
                        ORDER BY optionID ASC
                    """, (tq,))
                    oids = [int(r["optionID"]) for r in cur.fetchall()]
                    if opt_idx < len(oids):
                        cur.execute("DELETE FROM Scenario_Option WHERE optionID = ?", (oids[opt_idx],))

        # ✅ ALWAYS cleanup after delete
        cleanup_orphan_translations(conn)
        conn.commit()
        
def ensure_mbti_result_profile_columns(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(MBTI_Result)")
    cols = [row["name"] for row in cur.fetchall()]

    if "profileSnapshot" not in cols:
        cur.execute("ALTER TABLE MBTI_Result ADD COLUMN profileSnapshot TEXT")

    if "contextSummary" not in cols:
        cur.execute("ALTER TABLE MBTI_Result ADD COLUMN contextSummary TEXT")

    conn.commit()
        
def cleanup_orphan_translations(conn):
    cur = conn.cursor()

    # BM/ZH rows are "orphan" only if their groupID no longer exists in EN groups
    cur.execute("""
        SELECT q.questionID
        FROM Scenario_Question q
        WHERE q.language IN ('BM','ZH')
          AND q.groupID IS NOT NULL
          AND q.groupID NOT IN (
              SELECT groupID
              FROM Scenario_Question
              WHERE language='EN' AND groupID IS NOT NULL
          )
    """)
    orphan_qids = [int(r["questionID"]) for r in cur.fetchall()]

    if orphan_qids:
        cur.executemany("DELETE FROM Scenario_Option WHERE questionID = ?", [(x,) for x in orphan_qids])
        cur.executemany("DELETE FROM Scenario_Question WHERE questionID = ?", [(x,) for x in orphan_qids])
        
def admin_delete_question(question_id: int):
    with get_conn() as conn:
        cur = conn.cursor()

        # 1) find the question row
        cur.execute("""
            SELECT questionID, groupID, category, language
            FROM Scenario_Question
            WHERE questionID = ?
        """, (int(question_id),))
        row = cur.fetchone()
        if not row:
            return

        qid = int(row["questionID"])
        group_id = int(row["groupID"] or qid)
        category = (row["category"] or "").strip()
        lang_now = (row["language"] or "EN").upper()

        qids_to_delete = set()

        # 2) A) normal: delete all questions in same groupID
        cur.execute("SELECT questionID FROM Scenario_Question WHERE groupID = ?", (group_id,))
        for r in cur.fetchall():
            qids_to_delete.add(int(r["questionID"]))

        # 3) B) fallback: delete BM/ZH that match the SAME SLOT (index) in this category
        #    IMPORTANT: compute BEFORE deleting anything
        def get_ids(lang: str):
            cur.execute("""
                SELECT questionID
                FROM Scenario_Question
                WHERE language = ? AND category = ?
                ORDER BY questionID ASC
            """, (lang, category))
            return [int(x["questionID"]) for x in cur.fetchall()]

        en_ids = get_ids("EN")
        bm_ids = get_ids("BM")
        zh_ids = get_ids("ZH")

        # determine idx
        idx = None

        # best case: group_id is the EN root id (your intended design)
        if group_id in en_ids:
            idx = en_ids.index(group_id)
        # else: if deleting EN row directly
        elif lang_now == "EN" and qid in en_ids:
            idx = en_ids.index(qid)
        # else: if deleting BM/ZH row and group broken, use its own list position
        elif lang_now == "BM" and qid in bm_ids:
            idx = bm_ids.index(qid)
        elif lang_now == "ZH" and qid in zh_ids:
            idx = zh_ids.index(qid)

        if idx is not None:
            if idx < len(en_ids): qids_to_delete.add(en_ids[idx])
            if idx < len(bm_ids): qids_to_delete.add(bm_ids[idx])
            if idx < len(zh_ids): qids_to_delete.add(zh_ids[idx])

        # 4) delete options + questions for all targets
        if qids_to_delete:
            cur.executemany(
                "DELETE FROM Scenario_Option WHERE questionID = ?",
                [(x,) for x in qids_to_delete]
            )
            cur.executemany(
                "DELETE FROM Scenario_Question WHERE questionID = ?",
                [(x,) for x in qids_to_delete]
            )
            
        cleanup_orphan_translations(conn)
        conn.commit()

def list_options_for_question(question_id: int, lang: str = "EN"):
    # accept EN / ZH / BM only
    lang = (lang or "EN").strip().upper()
    if lang not in ("EN", "ZH", "BM"):
        lang = "EN"

    conn = get_conn()
    cur = conn.cursor()

    # If your Scenario_Option table has NO language column, lang is only for compatibility
    cur.execute("""
        SELECT optionID, optionKey, optionText, EIScore, SNScore, TFScore, JPScore
        FROM Scenario_Option
        WHERE questionID = ?
        ORDER BY optionKey ASC
    """, (question_id,))

    rows = cur.fetchall()
    conn.close()
    return rows

def get_option_by_id(option_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT optionID, questionID, optionText, EIScore, SNScore, TFScore, JPScore
        FROM Scenario_Option
        WHERE optionID = ?
    """, (option_id,))
    row = cur.fetchone()
    conn.close()
    return row
    
def ensure_career_text_table(conn):
    cur = conn.cursor()

    # 1) Create table if it doesn't exist (correct schema)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Career_Text (
            careerKey TEXT NOT NULL,
            language  TEXT NOT NULL DEFAULT 'EN',
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            UNIQUE(careerKey, language)
        )
    """)

    # 2) If table exists but missing columns, add them
    cur.execute("PRAGMA table_info(Career_Text)")
    cols = [r["name"] for r in cur.fetchall()]

    if "lang" in cols and "language" not in cols:
        # add new column
        cur.execute("ALTER TABLE Career_Text ADD COLUMN language TEXT NOT NULL DEFAULT 'EN'")
        # copy values
        cur.execute("UPDATE Career_Text SET language = lang WHERE (language IS NULL OR language = '')")
        conn.commit()

    conn.commit()
    
    

# helper (get by email already exists)
def verify_user(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE User SET isVerified = 1 WHERE userID = ?", (user_id,))
        conn.commit()
    
def migrate_career_text_table(conn):
    cur = conn.cursor()

    # table exists?
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Career_Text'")
    if not cur.fetchone():
        return  # not exist yet, no migration needed

    # check columns
    cur.execute("PRAGMA table_info(Career_Text)")
    cols = [r["name"] for r in cur.fetchall()]

    # check if we already have a UNIQUE index on (careerKey, language)
    cur.execute("PRAGMA index_list(Career_Text)")
    idxs = cur.fetchall()
    has_unique = False
    for idx in idxs:
        if int(idx["unique"]) == 1:
            # inspect index columns
            cur.execute(f"PRAGMA index_info({idx['name']})")
            icols = [r["name"] for r in cur.fetchall()]
            if icols == ["careerKey", "language"] or set(icols) == {"careerKey", "language"}:
                has_unique = True
                break

    # If missing UNIQUE OR missing correct columns -> rebuild table
    if (not has_unique) or ("language" not in cols):
        cur.execute("ALTER TABLE Career_Text RENAME TO Career_Text_old")

        # create correct table
        cur.execute("""
            CREATE TABLE Career_Text (
                careerKey TEXT NOT NULL,
                language  TEXT NOT NULL DEFAULT 'EN',
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                UNIQUE(careerKey, language)
            )
        """)

        # copy data from old table (support old schema that had "lang" or "language")
        cur.execute("PRAGMA table_info(Career_Text_old)")
        old_cols = [r["name"] for r in cur.fetchall()]

        if "language" in old_cols:
            cur.execute("""
                INSERT INTO Career_Text(careerKey, language, title, description)
                SELECT careerKey, UPPER(language), title, description
                FROM Career_Text_old
            """)
        elif "lang" in old_cols:
            cur.execute("""
                INSERT INTO Career_Text(careerKey, language, title, description)
                SELECT careerKey, UPPER(lang), title, description
                FROM Career_Text_old
            """)
        else:
            # if somehow no lang/language, just keep EN
            cur.execute("""
                INSERT INTO Career_Text(careerKey, language, title, description)
                SELECT careerKey, 'EN', title, description
                FROM Career_Text_old
            """)

        cur.execute("DROP TABLE Career_Text_old")
        conn.commit()

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # ---- User ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS User (
        userID INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        name TEXT,
        passwordHash TEXT NOT NULL,
        createdAt TEXT NOT NULL,
        isVerified INTEGER NOT NULL DEFAULT 0
    )
    """)
    
    # ---- User Profile ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS User_Profile (
        profileID INTEGER PRIMARY KEY AUTOINCREMENT,
        userID INTEGER NOT NULL UNIQUE,
        ageRange TEXT,
        educationLevel TEXT,
        fieldOfStudy TEXT,
        currentOccupation TEXT,
        skills TEXT,
        interests TEXT,
        preferredWorkStyle TEXT,
        careerGoal TEXT,
        profileSource TEXT DEFAULT 'manual',
        profileCompleted INTEGER NOT NULL DEFAULT 0,
        createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
        updatedAt TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(userID) REFERENCES User(userID)
    )
    """)

    # ---- MBTI ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS MBTI_Type (
        mbtiTypeID INTEGER PRIMARY KEY AUTOINCREMENT,
        typeCode TEXT NOT NULL UNIQUE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS MBTI_Result (
        resultID INTEGER PRIMARY KEY AUTOINCREMENT,
        userID INTEGER NOT NULL,
        mbtiTypeID INTEGER NOT NULL,
        confidenceScore REAL NOT NULL,
        rawText TEXT,
        createdAt TEXT NOT NULL,
        FOREIGN KEY(userID) REFERENCES User(userID),
        FOREIGN KEY(mbtiTypeID) REFERENCES MBTI_Type(mbtiTypeID)
    )
    """)

    # ---- Scenario ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS Scenario_Question (
        questionID INTEGER PRIMARY KEY AUTOINCREMENT,
        groupID INTEGER,
        language TEXT NOT NULL DEFAULT 'EN',
        category TEXT NOT NULL,
        scenarioText TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS Scenario_Option (
        optionID INTEGER PRIMARY KEY AUTOINCREMENT,
        questionID INTEGER NOT NULL,
        optionKey TEXT NOT NULL DEFAULT '',
        optionText TEXT NOT NULL,
        EIScore INTEGER NOT NULL DEFAULT 0,
        SNScore INTEGER NOT NULL DEFAULT 0,
        TFScore INTEGER NOT NULL DEFAULT 0,
        JPScore INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(questionID) REFERENCES Scenario_Question(questionID)
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS MBTI_Career (
        careerID INTEGER PRIMARY KEY AUTOINCREMENT,
        typeCode TEXT NOT NULL,          -- e.g. INTJ
        careerKey TEXT NOT NULL,         -- e.g. ux_researcher
        url TEXT NOT NULL,
        sortOrder INTEGER NOT NULL DEFAULT 1,
        UNIQUE(typeCode, careerKey),
        FOREIGN KEY(typeCode) REFERENCES MBTI_Type(typeCode)
    )
    """)

    conn.commit()

    # ---- migrations / ensure columns ----
    ensure_user_preferred_language(conn)
    ensure_user_is_admin(conn)
    migrate_add_group_id(conn)
    migrate_add_option_key(conn)
    migrate_career_text_table(conn)
    ensure_career_text_table(conn)
    ensure_mbti_result_profile_columns(conn)

    conn.commit()
    conn.close()
    
def get_mbti_type_id(type_code: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT mbtiTypeID FROM MBTI_Type WHERE typeCode = ?", (type_code,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise ValueError(f"MBTI type not found: {type_code}")
    return int(row["mbtiTypeID"])

def create_result_with_time(user_id: int, type_code: str, confidence: float,
                            raw_text: str, created_at: str, is_demo: int = 0,
                            profile_snapshot=None, context_summary=None):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT mbtiTypeID FROM MBTI_Type WHERE typeCode = ?", (type_code,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO MBTI_Type(typeCode) VALUES(?)", (type_code,))
        mbti_type_id = cur.lastrowid
        conn.commit()
    else:
        mbti_type_id = row["mbtiTypeID"]

    if profile_snapshot is None:
        profile_snapshot = build_profile_snapshot(user_id)

    if context_summary is None:
        context_summary = build_context_summary(profile_snapshot)

    snapshot_json = json.dumps(profile_snapshot, ensure_ascii=False)

    cur.execute("""
        INSERT INTO MBTI_Result (
            userID, mbtiTypeID, confidenceScore, rawText, createdAt,
            profileSnapshot, contextSummary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        mbti_type_id,
        float(confidence),
        raw_text,
        created_at,
        snapshot_json,
        context_summary
    ))
    conn.commit()
    conn.close()

def admin_list_careers(type_code: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    if type_code:
        cur.execute("""
            SELECT careerID, typeCode, careerKey, url, sortOrder
            FROM MBTI_Career
            WHERE typeCode = ?
            ORDER BY sortOrder ASC
        """, (type_code.upper(),))
    else:
        cur.execute("""
            SELECT careerID, typeCode, careerKey, url, sortOrder
            FROM MBTI_Career
            ORDER BY typeCode ASC, sortOrder ASC
        """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def admin_get_career(career_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT careerID, typeCode, careerKey, url, sortOrder
        FROM MBTI_Career
        WHERE careerID = ?
    """, (career_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def admin_create_career(type_code: str, career_key: str, url: str, sort_order: int):
    type_code = (type_code or "").strip().upper()
    career_key = (career_key or "").strip().lower()
    url = (url or "").strip()
    sort_order = int(sort_order) if str(sort_order).strip() else 1

    with get_conn() as conn:
        cur = conn.cursor()

        # ✅ Insert or Update if exists
        cur.execute("""
            INSERT INTO MBTI_Career(typeCode, careerKey, url, sortOrder)
            VALUES(?,?,?,?)
            ON CONFLICT(typeCode, careerKey) DO UPDATE SET
                url = excluded.url,
                sortOrder = excluded.sortOrder
        """, (type_code, career_key, url, sort_order))

        conn.commit()

        # ✅ return careerID (existing or new)
        cur.execute("""
            SELECT careerID FROM MBTI_Career
            WHERE typeCode = ? AND careerKey = ?
        """, (type_code, career_key))
        row = cur.fetchone()
        return int(row["careerID"]) if row else None


def admin_update_career(career_id: int, career_key: str, url: str, sort_order: int):
    career_key = (career_key or "").strip().lower()
    url = (url or "").strip()

    with get_conn() as conn:
        conn.execute("""
            UPDATE MBTI_Career
            SET careerKey = ?, url = ?, sortOrder = ?
            WHERE careerID = ?
        """, (career_key, url, int(sort_order), int(career_id)))
        conn.commit()

def admin_delete_career(career_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM MBTI_Career WHERE careerID = ?", (int(career_id),))
        conn.commit()
    
def admin_get_career_text(career_key: str):
    career_key = (career_key or "").strip().lower()
    with get_conn() as conn:
        ensure_career_text_table(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT language, title, description
            FROM Career_Text
            WHERE careerKey = ?
        """, (career_key,))
        rows = cur.fetchall()

    out = {"EN": {"title": "", "description": ""},
           "BM": {"title": "", "description": ""},
           "ZH": {"title": "", "description": ""}}
    for r in rows:
        lang = (r["language"] or "EN").upper()
        if lang in out:
            out[lang]["title"] = r["title"] or ""
            out[lang]["description"] = r["description"] or ""
    return out   

def admin_upsert_career_text(career_key: str, language: str, title: str, description: str):
    career_key = (career_key or "").strip().lower()
    language = (language or "EN").strip().upper()
    if language not in ("EN", "BM", "ZH"):
        language = "EN"

    title = (title or "").strip()
    description = (description or "").strip()

    with get_conn() as conn:
        ensure_career_text_table(conn)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO Career_Text (careerKey, language, title, description)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(careerKey, language) DO UPDATE SET
                title = excluded.title,
                description = excluded.description
        """, (career_key, language, title, description))
        conn.commit()

def list_careers_for_type(type_code: str, lang: str = "EN"):
    lang = (lang or "EN").strip().upper()
    if lang not in ("EN", "BM", "ZH"):
        lang = "EN"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
      SELECT c.careerKey, c.url, c.sortOrder,
             COALESCE(t.title,'') AS title,
             COALESCE(t.description,'') AS description
      FROM MBTI_Career c
      LEFT JOIN Career_Text t
        ON t.careerKey = c.careerKey AND t.language = ?
      WHERE c.typeCode = ?
      ORDER BY c.sortOrder ASC
    """, (lang, type_code))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def migrate_add_option_key(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(Scenario_Option)")
    cols = [row["name"] for row in cur.fetchall()]

    # add column if missing
    if "optionKey" not in cols:
        cur.execute("ALTER TABLE Scenario_Option ADD COLUMN optionKey TEXT NOT NULL DEFAULT ''")
        conn.commit()

    # fill optionKey for existing rows (A/B/C/D per question)
    cur.execute("SELECT questionID FROM Scenario_Question ORDER BY questionID")
    qids = [r["questionID"] for r in cur.fetchall()]

    for qid in qids:
        cur.execute("""
            SELECT optionID
            FROM Scenario_Option
            WHERE questionID = ?
            ORDER BY optionID
        """, (qid,))
        oids = [r["optionID"] for r in cur.fetchall()]

        for i, oid in enumerate(oids):
            key = "ABCD"[i] if i < 4 else str(i + 1)
            cur.execute("""
                UPDATE Scenario_Option
                SET optionKey = ?
                WHERE optionID = ?
                  AND (optionKey IS NULL OR optionKey = '')
            """, (key, oid))

    conn.commit()

def ensure_user_preferred_language(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(User)")
    cols = [row["name"] for row in cur.fetchall()]
    if "preferredLanguage" not in cols:
        cur.execute("ALTER TABLE User ADD COLUMN preferredLanguage TEXT DEFAULT 'EN'")
        conn.commit()

# ---------- User ----------
def create_user(email: str, name: str, password_hash: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO User (email, name, passwordHash, createdAt, isVerified, preferredLanguage)
            VALUES (?, ?, ?, ?, 0, 'EN')
        """, (email, name, password_hash, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return cur.lastrowid

def get_user_profile_by_user_id(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM User_Profile
        WHERE userID = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user_profile(
    user_id: int,
    age_range: str,
    education_level: str,
    field_of_study: str,
    current_occupation: str,
    skills: str,
    interests: str,
    preferred_work_style: str,
    career_goal: str,
    profile_source: str = "manual",
    profile_completed: int = 1
):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO User_Profile (
            userID, ageRange, educationLevel, fieldOfStudy,
            currentOccupation, skills, interests,
            preferredWorkStyle, careerGoal,
            profileSource, profileCompleted
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, age_range, education_level, field_of_study,
        current_occupation, skills, interests,
        preferred_work_style, career_goal,
        profile_source, profile_completed
    ))
    conn.commit()
    conn.close()

def update_user_profile_manual(
    user_id: int,
    age_range: str,
    education_level: str,
    field_of_study: str,
    current_occupation: str,
    skills: str,
    interests: str,
    preferred_work_style: str,
    career_goal: str,
    profile_source: str = "manual",
    profile_completed: int = 1
):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE User_Profile
        SET ageRange = ?,
            educationLevel = ?,
            fieldOfStudy = ?,
            currentOccupation = ?,
            skills = ?,
            interests = ?,
            preferredWorkStyle = ?,
            careerGoal = ?,
            profileSource = ?,
            profileCompleted = ?,
            updatedAt = CURRENT_TIMESTAMP
        WHERE userID = ?
    """, (
        age_range, education_level, field_of_study,
        current_occupation, skills, interests,
        preferred_work_style, career_goal,
        profile_source, profile_completed,
        user_id
    ))
    conn.commit()
    conn.close()

def upsert_user_profile_manual(
    user_id: int,
    age_range: str,
    education_level: str,
    field_of_study: str,
    current_occupation: str,
    skills: str,
    interests: str,
    preferred_work_style: str,
    career_goal: str,
    profile_source: str = "manual",
    profile_completed: int = 1
):
    existing = get_user_profile_by_user_id(user_id)
    if existing:
        update_user_profile_manual(
            user_id, age_range, education_level, field_of_study,
            current_occupation, skills, interests,
            preferred_work_style, career_goal,
            profile_source, profile_completed
        )
    else:
        create_user_profile(
            user_id, age_range, education_level, field_of_study,
            current_occupation, skills, interests,
            preferred_work_style, career_goal,
            profile_source, profile_completed
        )

def get_user_by_email(email: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM User WHERE email = ?", (email.strip().lower(),))
    row = cur.fetchone()
    conn.close()
    return row

def get_user_by_id(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM User WHERE userID = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_profile(user_id: int, name: str, email: str):
    """Update name + email. Email must remain unique."""
    email = email.strip().lower()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE User
        SET name = ?, email = ?
        WHERE userID = ?
    """, (name.strip(), email, user_id))
    conn.commit()
    conn.close()

def update_user_language(user_id: int, lang: str):
    lang = (lang or "EN").strip().upper()
    if lang not in ["EN", "ZH", "BM"]:
        lang = "EN"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE User SET preferredLanguage = ? WHERE userID = ?", (lang, user_id))
    conn.commit()
    conn.close()

def update_user_password_hash(user_id: int, new_hash: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE User SET passwordHash = ? WHERE userID = ?", (new_hash, user_id))
    conn.commit()
    conn.close()

# ---------- MBTI types ----------
def list_mbti_types():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT mbtiTypeID, typeCode FROM MBTI_Type ORDER BY typeCode")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_mbti_type_id(type_code: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT mbtiTypeID FROM MBTI_Type WHERE typeCode = ?", (type_code,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise ValueError("Unknown MBTI type code")
    return int(row["mbtiTypeID"])

# ---------- Results CRUD ----------
def create_result(user_id, type_code, confidence, raw_text, created_at=None,
                  profile_snapshot=None, context_summary=None):
    conn = get_conn()
    cur = conn.cursor()

    # 1) get mbtiTypeID
    cur.execute("SELECT mbtiTypeID FROM MBTI_Type WHERE typeCode=?", (type_code,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO MBTI_Type(typeCode) VALUES(?)", (type_code,))
        mbti_type_id = cur.lastrowid
    else:
        mbti_type_id = row["mbtiTypeID"] if hasattr(row, "__getitem__") else row[0]

    # 2) createdAt
    if not created_at:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 3) default snapshot if not given
    if profile_snapshot is None:
        profile_snapshot = build_profile_snapshot(user_id)

    if context_summary is None:
        context_summary = build_context_summary(profile_snapshot)

    snapshot_json = json.dumps(profile_snapshot, ensure_ascii=False)

    # 4) insert result
    cur.execute("""
        INSERT INTO MBTI_Result(
            userID, mbtiTypeID, confidenceScore, rawText, createdAt,
            profileSnapshot, contextSummary
        )
        VALUES(?,?,?,?,?,?,?)
    """, (
        user_id,
        mbti_type_id,
        confidence,
        raw_text,
        created_at,
        snapshot_json,
        context_summary
    ))

    conn.commit()
    conn.close()

def list_results_for_user(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.resultID, t.typeCode, r.confidenceScore, r.rawText, r.createdAt,
               r.profileSnapshot, r.contextSummary
        FROM MBTI_Result r
        JOIN MBTI_Type t ON r.mbtiTypeID = t.mbtiTypeID
        WHERE r.userID = ?
        ORDER BY datetime(createdAt) DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def list_results_for_user_filtered(user_id: int, start_date: str = None, end_date: str = None):
    """
    start_date/end_date: 'YYYY-MM-DD'
    依赖 SQLite 的 date(createdAt) 做范围过滤
    """
    conn = get_conn()
    cur = conn.cursor()

    sql = """
        SELECT r.resultID, r.userID, t.typeCode, r.confidenceScore, r.rawText, r.createdAt,
               r.profileSnapshot, r.contextSummary
        FROM MBTI_Result r
        JOIN MBTI_Type t ON r.mbtiTypeID = t.mbtiTypeID
        WHERE r.userID = ?
    """
    params = [user_id]

    if start_date and end_date:
        sql += " AND date(r.createdAt) BETWEEN date(?) AND date(?) "
        params += [start_date, end_date]
    elif start_date:
        sql += " AND date(r.createdAt) >= date(?) "
        params += [start_date]
    elif end_date:
        sql += " AND date(r.createdAt) <= date(?) "
        params += [end_date]

    sql += " ORDER BY r.createdAt DESC "

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_result_for_user(result_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.resultID, t.typeCode, r.confidenceScore, r.rawText, r.createdAt,
               r.profileSnapshot, r.contextSummary
        FROM MBTI_Result r
        JOIN MBTI_Type t ON r.mbtiTypeID = t.mbtiTypeID
        WHERE r.resultID = ? AND r.userID = ?
    """, (result_id, user_id))
    row = cur.fetchone()
    conn.close()
    return row

def update_result(result_id: int, user_id: int, type_code: str, confidence: float, raw_text: str):
    mbti_id = get_mbti_type_id(type_code)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE MBTI_Result
        SET mbtiTypeID = ?, confidenceScore = ?, rawText = ?
        WHERE resultID = ? AND userID = ?
    """, (mbti_id, float(confidence), raw_text, result_id, user_id))
    conn.commit()
    conn.close()

def delete_result(result_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM MBTI_Result WHERE resultID = ? AND userID = ?", (result_id, user_id))
    conn.commit()
    conn.close()

def admin_list_users(q: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    if q:
        cur.execute("""
            SELECT userID, name, email, isAdmin, isVerified, preferredLanguage
            FROM user
            WHERE lower(name) LIKE ? OR lower(email) LIKE ?
            ORDER BY userID DESC
        """, (f"%{q}%", f"%{q}%"))
    else:
        cur.execute("""
            SELECT userID, name, email, isAdmin, isVerified, preferredLanguage
            FROM user
            ORDER BY userID DESC
        """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def admin_set_user_password(user_id: int, password_hash: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE user SET passwordHash=? WHERE userID=?", (password_hash, user_id))
    conn.commit()
    conn.close()
    
def migrate_add_group_id(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(Scenario_Question)")
    cols = [row["name"] for row in cur.fetchall()]

    # 1) add column if missing
    if "groupID" not in cols:
        cur.execute("ALTER TABLE Scenario_Question ADD COLUMN groupID INTEGER")
        conn.commit()

    # 2) backfill: for existing old data, groupID = questionID (no linkage info available)
    cur.execute("""
        UPDATE Scenario_Question
        SET groupID = questionID
        WHERE groupID IS NULL
    """)
    conn.commit()
    
def admin_get_question_by_group(group_id: int, language: str):
    language = (language or "EN").strip().upper()
    if language not in ("EN", "ZH", "BM"):
        language = "EN"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM Scenario_Question
        WHERE groupID = ? AND language = ?
        LIMIT 1
    """, (int(group_id), language))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def admin_upsert_question_translation(group_id: int, language: str, category: str, scenario_text: str) -> int:
    """
    Create or update the translated question row under the same groupID.
    Returns the translated questionID.
    """
    language = (language or "EN").strip().upper()
    if language not in ("EN", "ZH", "BM"):
        language = "EN"

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT questionID FROM Scenario_Question
            WHERE groupID = ? AND language = ?
            LIMIT 1
        """, (int(group_id), language))
        row = cur.fetchone()

        if row:
            qid = int(row["questionID"])
            cur.execute("""
                UPDATE Scenario_Question
                SET category = ?, scenarioText = ?
                WHERE questionID = ?
            """, (category, scenario_text, qid))
            conn.commit()
            return qid

        # create new translation row
        cur.execute("""
            INSERT INTO Scenario_Question (language, category, scenarioText, groupID)
            VALUES (?, ?, ?, ?)
        """, (language, category, scenario_text, int(group_id)))
        qid = cur.lastrowid
        conn.commit()
        return qid


def ensure_default_options(question_id: int):
    """
    Ensure option keys A-D exist for a given question_id.
    """
    keys = ["A", "B", "C", "D"]
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT optionKey FROM Scenario_Option
            WHERE questionID = ?
        """, (int(question_id),))
        existing = {r["optionKey"] for r in cur.fetchall()}

        to_add = [(question_id, k, "") for k in keys if k not in existing]
        if to_add:
            cur.executemany("""
                INSERT INTO Scenario_Option (questionID, optionKey, optionText, EIScore, SNScore, TFScore, JPScore)
                VALUES (?, ?, ?, 0, 0, 0, 0)
            """, to_add)
            conn.commit()

def admin_get_question_by_group_lang(groupID: int, lang: str):
    conn = get_conn()
    cur = conn.cursor()
    lang = (lang or "EN").upper()
    cur.execute("""
        SELECT questionID, groupID, category, scenarioText, language
        FROM Scenario_Question
        WHERE groupID = ? AND language = ?
        LIMIT 1
    """, (int(groupID), lang))
    row = cur.fetchone()
    conn.close()
    return row

def get_question_ids_by_group(group_id: int) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT language, questionID
        FROM Scenario_Question
        WHERE groupID = ?
    """, (int(group_id),))
    rows = cur.fetchall()
    conn.close()

    out = {}
    for r in rows:
        out[(r["language"] or "EN").upper()] = int(r["questionID"])
    return out

def admin_update_option_by_question_key(question_id: int, option_key: str, option_text: str):
    option_key = (option_key or "").strip().upper()
    if option_key not in ("A","B","C","D"):
        return

    with get_conn() as conn:
        conn.execute("""
            UPDATE Scenario_Option
            SET optionText = ?
            WHERE questionID = ? AND optionKey = ?
        """, (option_text.strip(), int(question_id), option_key))
        conn.commit()
        
def admin_update_option_by_question_key_full(question_id: int, option_key: str,
                                            option_text: str, ei: int, sn: int, tf: int, jp: int):
    option_key = (option_key or "").strip().upper()
    if option_key not in ("A", "B", "C", "D"):
        return

    with get_conn() as conn:
        conn.execute("""
            UPDATE Scenario_Option
            SET optionText = ?,
                EIScore = ?, SNScore = ?, TFScore = ?, JPScore = ?
            WHERE questionID = ? AND optionKey = ?
        """, (option_text.strip(), int(ei), int(sn), int(tf), int(jp),
              int(question_id), option_key))
        conn.commit()
        
def admin_list_scenario_questions_en():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT questionID, groupID, category, scenarioText, language
        FROM Scenario_Question
        WHERE language='EN'
        ORDER BY groupID ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def copy_options_from_question(src_qid: int, dst_qid: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT optionKey, optionText, EIScore, SNScore, TFScore, JPScore
        FROM Scenario_Option
        WHERE questionID=?
        ORDER BY optionKey ASC
    """, (int(src_qid),))
    src_opts = cur.fetchall()

    for o in src_opts:
        cur.execute("""
            UPDATE Scenario_Option
            SET optionText=?, EIScore=?, SNScore=?, TFScore=?, JPScore=?
            WHERE questionID=? AND optionKey=?
        """, (o["optionText"], o["EIScore"], o["SNScore"], o["TFScore"], o["JPScore"],
              int(dst_qid), o["optionKey"]))

    conn.commit()
    conn.close()
    
def build_profile_snapshot(user_id: int):
    user = get_user_by_id(user_id) or {}
    profile = get_user_profile_by_user_id(user_id) or {}

    snapshot = {
        "userID": user_id,
        "name": user.get("name", ""),
        "email": user.get("email", ""),
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

    return snapshot

def build_context_summary(profile_snapshot: dict) -> str:
    if not profile_snapshot:
        return ""

    parts = []

    education = (profile_snapshot.get("educationLevel") or "").strip()
    field = (profile_snapshot.get("fieldOfStudy") or "").strip()
    occupation = (profile_snapshot.get("currentOccupation") or "").strip()
    interests = (profile_snapshot.get("interests") or "").strip()
    work_style = (profile_snapshot.get("preferredWorkStyle") or "").strip()
    career_goal = (profile_snapshot.get("careerGoal") or "").strip()

    if education:
        parts.append(f"Education: {education}")
    if field:
        parts.append(f"Field: {field}")
    if occupation:
        parts.append(f"Occupation: {occupation}")
    if interests:
        parts.append(f"Interests: {interests}")
    if work_style:
        parts.append(f"Work style: {work_style}")
    if career_goal:
        parts.append(f"Career goal: {career_goal}")

    return " | ".join(parts)
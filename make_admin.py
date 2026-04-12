import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "mbti.db")

EMAIL_TO_MAKE_ADMIN = "yxin62477@gmail.com"   # ✅ put here

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ensure isAdmin column exists
cur.execute("PRAGMA table_info(User)")
cols = [r[1] for r in cur.fetchall()]
if "isAdmin" not in cols:
    cur.execute("ALTER TABLE User ADD COLUMN isAdmin INTEGER NOT NULL DEFAULT 0")
    conn.commit()

# update user
cur.execute("UPDATE User SET isAdmin=1 WHERE email=?", (EMAIL_TO_MAKE_ADMIN,))
conn.commit()

# verify
cur.execute("SELECT userID, email, isAdmin FROM User WHERE email=?", (EMAIL_TO_MAKE_ADMIN,))
print(cur.fetchone())

conn.close()
print("Done")

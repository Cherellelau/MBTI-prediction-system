import sqlite3

DB_PATH = "mbti.db"

NEW_EMAIL = "cherellellx-wp22@student.tarc.edu.my"
OLD_EMAIL = "yxin62477@gmail.com"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("UPDATE User SET isAdmin = 1 WHERE email = ?", (NEW_EMAIL,))
cur.execute("UPDATE User SET isAdmin = 0 WHERE email = ?", (OLD_EMAIL,))

conn.commit()
conn.close()
print("Done. Admin updated.")

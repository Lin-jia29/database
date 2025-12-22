import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "product.db")


def create_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS Product (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        company TEXT,
        main_category TEXT,
        description TEXT,

        eligible_age_min INTEGER,
        eligible_age_max INTEGER,

        is_online INTEGER DEFAULT 0,
        is_bank INTEGER DEFAULT 0,
        is_group INTEGER DEFAULT 0,

        score REAL DEFAULT 0,
        rating REAL DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()
    print("✅ product.db 初始化完成")


if __name__ == "__main__":
    create_db()
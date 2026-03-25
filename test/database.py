import psycopg2
import os

# 🔐 Get database URL from environment (Render / local .env)
DATABASE_URL = os.getenv("DATABASE_URL")

# ------------------ CONNECTION ------------------
def get_connection():
    return psycopg2.connect(DATABASE_URL)

# ------------------ INIT DATABASE ------------------
def init_db():
    conn = get_connection()
    c = conn.cursor()

    # ---------- USERS TABLE ----------
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        user_key BYTEA NOT NULL
    )
    """)

    # ---------- DOCUMENTS TABLE ----------
    c.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        filename BYTEA NOT NULL,
        filesize INTEGER,
        upload_time TEXT,
        encrypted_data BYTEA NOT NULL
    )
    """)

    # ---------- KEYWORDS TABLE ----------
    c.execute("""
    CREATE TABLE IF NOT EXISTS keywords (
        id SERIAL PRIMARY KEY,
        doc_id INTEGER REFERENCES documents(id),
        keyword_hash TEXT
    )
    """)

    # 🔥 PERFORMANCE BOOST (IMPORTANT)
    c.execute("CREATE INDEX IF NOT EXISTS idx_keywords_hash ON keywords(keyword_hash)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id)")

    conn.commit()
    conn.close()
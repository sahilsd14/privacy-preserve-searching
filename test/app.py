from flask import Flask, render_template, request, redirect, session, send_file
import hashlib, re, io, datetime, os
from cryptography.fernet import Fernet
import pdfplumber

from database import get_connection, init_db

app = Flask(__name__)
app.secret_key = "secret"

init_db()

# ------------------ STOPWORDS ------------------
stopwords = {"the","is","in","and","to","of","a","on","for","with","as","by"}

# ------------------ USER KEY ------------------
def get_user_cipher(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_key FROM users WHERE id=%s", (user_id,))
    key = c.fetchone()[0]
    conn.close()
    return Fernet(bytes(key))

# ------------------ HOME ------------------
@app.route("/")
def home():
    return redirect("/login")

# ------------------ LOGIN ------------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = hashlib.sha256(request.form["password"].encode()).hexdigest()

        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=%s AND password=%s", (username,password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user_id"] = user[0]
            return redirect("/dashboard")

        return "Invalid credentials"

    return render_template("login.html")

# ------------------ REGISTER ------------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = hashlib.sha256(request.form["password"].encode()).hexdigest()
        key = Fernet.generate_key()

        conn = get_connection()
        c = conn.cursor()

        try:
            c.execute(
                "INSERT INTO users(username,password,user_key) VALUES (%s,%s,%s)",
                (username,password,key)
            )
            conn.commit()
        except:
            return "User already exists"

        conn.close()
        return redirect("/login")

    return render_template("register.html")

# ------------------ DASHBOARD ------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=%s", (session["user_id"],))
    user = c.fetchone()[0]
    conn.close()

    is_admin = (user == "admin")

    return render_template("dashboard.html", is_admin=is_admin)

# ------------------ LOGOUT ------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------ UPLOAD ------------------
@app.route("/upload", methods=["GET","POST"])
def upload():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=%s", (session["user_id"],))
    user = c.fetchone()[0]
    conn.close()

    if user == "admin":
        return "Admin cannot upload files"

    if request.method == "POST":
        file = request.files["file"]
        filename = file.filename

        # TEXT EXTRACTION
        if filename.endswith(".txt"):
            data = file.read().decode("utf-8", errors="ignore")

        elif filename.endswith(".pdf"):
            data = ""
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        data += text
        else:
            return "Only TXT/PDF allowed"

        if not data.strip():
            return "Empty file"

        cipher = get_user_cipher(session["user_id"])

        # ENCRYPT
        encrypted_data = cipher.encrypt(data.encode())
        encrypted_filename = cipher.encrypt(filename.encode())

        conn = get_connection()
        c = conn.cursor()

        c.execute("""
        INSERT INTO documents(user_id,filename,filesize,upload_time,encrypted_data)
        VALUES (%s,%s,%s,%s,%s)
        """,(session["user_id"], encrypted_filename, len(data),
             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             encrypted_data))

        doc_id = c.fetchone()  # PostgreSQL needs RETURNING if required

        # GET LAST INSERT ID
        c.execute("SELECT currval(pg_get_serial_sequence('documents','id'))")
        doc_id = c.fetchone()[0]

        # HASH KEYWORDS
        words = set(re.findall(r'\b\w+\b', data.lower()))
        words = [w for w in words if w not in stopwords]

        for w in words:
            h = hashlib.sha256(w.encode()).hexdigest()
            c.execute("INSERT INTO keywords(doc_id,keyword_hash) VALUES (%s,%s)", (doc_id,h))

        conn.commit()
        conn.close()

        return redirect("/upload")

    return render_template("upload.html")

# ------------------ SEARCH ------------------
@app.route("/search", methods=["GET","POST"])
def search():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=%s", (session["user_id"],))
    user = c.fetchone()[0]
    conn.close()

    if user == "admin":
        return "Admin cannot search files"

    if request.method == "POST":
        query = request.form["keyword"].lower()

        words = re.findall(r'\b\w+\b', query)
        hashes = [hashlib.sha256(w.encode()).hexdigest() for w in words]

        conn = get_connection()
        c = conn.cursor()

        placeholders = ",".join(["%s"] * len(hashes))

        query_sql = f"""
        SELECT documents.id, documents.filename, documents.filesize,
               documents.upload_time, COUNT(*) as match_count
        FROM documents
        JOIN keywords ON documents.id = keywords.doc_id
        WHERE keywords.keyword_hash IN ({placeholders})
        AND documents.user_id=%s
        GROUP BY documents.id
        ORDER BY match_count DESC
        """

        c.execute(query_sql, (*hashes, session["user_id"]))
        results = c.fetchall()
        conn.close()

        cipher = get_user_cipher(session["user_id"])

        docs = []
        for r in results:
            decrypted_name = cipher.decrypt(bytes(r[1])).decode()

            docs.append({
                "id": r[0],
                "filename": decrypted_name,
                "filesize": r[2],
                "upload_time": r[3],
                "count": r[4]
            })

        return render_template("results.html", docs=docs)

    return render_template("search.html")

# ------------------ DOWNLOAD ------------------
@app.route("/download/<int:id>")
def download(id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    SELECT filename, encrypted_data 
    FROM documents 
    WHERE id=%s AND user_id=%s
    """,(id, session["user_id"]))

    file = c.fetchone()
    conn.close()

    if not file:
        return "File not found"

    cipher = get_user_cipher(session["user_id"])

    decrypted_file = cipher.decrypt(bytes(file[1]))
    decrypted_name = cipher.decrypt(bytes(file[0])).decode()

    return send_file(io.BytesIO(decrypted_file),
                     download_name=decrypted_name,
                     as_attachment=True)

# ------------------ ADMIN ------------------
@app.route("/admin")
def admin():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT username FROM users WHERE id=%s", (session["user_id"],))
    user = c.fetchone()[0]

    if user != "admin":
        return "Access Denied"

    users = c.execute("SELECT id, username FROM users")
    users = c.fetchall()

    documents = c.execute("""
    SELECT id, filename, filesize, upload_time
    FROM documents
    """)
    documents = c.fetchall()

    keywords = c.execute("""
    SELECT doc_id, STRING_AGG(keyword_hash, ',')
    FROM keywords
    GROUP BY doc_id
    """)
    keywords = c.fetchall()

    conn.close()

    return render_template("admin.html",
                           users=users,
                           documents=documents,
                           keywords=keywords)

# ------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
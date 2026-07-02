"""
MUSIC SERENIA - app.py
Flat file-structure Flask backend (no subfolders).
Serves all HTML pages directly from the project root, uses data.dat as a
flat-file database (one JSON object per line) for users, admin, page
content, and song metadata. Uploaded cover images / audio files are also
stored flat in this same root folder.
Render-ready: binds to 0.0.0.0 and reads PORT from the environment.
"""

import os
import json
import uuid
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.dat")

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"   # change this after first login

# Simple in-memory session store: token -> username (fine for a single
# small admin app; resets if the server restarts).
ADMIN_SESSIONS = {}

# Default copy for every footer page. Admin can overwrite these later.
PAGE_DEFAULTS = {
    "features": ("Features", "Discover Smart Library, Cloud Sync, Offline Mode, and Mood Playlists — everything built to keep you close to your music."),
    "plans":    ("Plans", "Free, Premium, and Family plans are available. Upgrade any time as your library grows."),
    "about":    ("About Us", "Music Serenia is a calm, personal home for the songs you love. We started this project to make listening feel less noisy and more intentional."),
    "careers":  ("Careers", "We're not hiring right now, but we're always glad to hear from people who care about music and design. Check back soon."),
    "contact":  ("Contact Us", "Have a question or found a bug? Reach us any time at support@musicserenia.example and we'll get back to you shortly."),
    "help-center": ("Help Center", "Looking for help with your account, playback, or downloads? Browse our guides or contact support for anything else."),
    "privacy":  ("Privacy Policy", "We only collect what's needed to run your account and library. We never sell your data. Full policy details coming soon."),
    "terms":    ("Terms of Service", "By using Music Serenia you agree to use the service fairly and respect the rights of artists and other listeners."),
}

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")


# ---------------------------------------------------------------------
# data.dat helpers
# ---------------------------------------------------------------------
def init_data_file():
    if not os.path.exists(DATA_FILE):
        open(DATA_FILE, "w", encoding="utf-8").close()


def read_records():
    records = []
    if not os.path.exists(DATA_FILE):
        return records
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def write_records(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def append_record(record):
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def find_user(username):
    for rec in read_records():
        if rec.get("type") == "user" and rec.get("username") == username:
            return rec
    return None


def find_admin(username):
    for rec in read_records():
        if rec.get("type") == "admin" and rec.get("username") == username:
            return rec
    return None


def get_page(key):
    for rec in read_records():
        if rec.get("type") == "page" and rec.get("key") == key:
            return rec
    return None


def upsert_page(key, title, body):
    records = read_records()
    found = False
    for rec in records:
        if rec.get("type") == "page" and rec.get("key") == key:
            rec["title"] = title
            rec["body"] = body
            found = True
            break
    if not found:
        records.append({"type": "page", "key": key, "title": title, "body": body})
    write_records(records)


def init_defaults():
    """Seed default admin account and default page content if missing."""
    records = read_records()
    changed = False

    if not any(r.get("type") == "admin" for r in records):
        records.append({
            "type": "admin",
            "username": DEFAULT_ADMIN_USERNAME,
            "password_hash": generate_password_hash(DEFAULT_ADMIN_PASSWORD),
        })
        changed = True

    existing_keys = {r.get("key") for r in records if r.get("type") == "page"}
    for key, (title, body) in PAGE_DEFAULTS.items():
        if key not in existing_keys:
            records.append({"type": "page", "key": key, "title": title, "body": body})
            changed = True

    if changed:
        write_records(records)


def require_admin():
    """Returns username if the request has a valid admin token, else None."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        return ADMIN_SESSIONS.get(token)
    return None


# ---------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------
@app.route("/")
def landing():
    return send_from_directory(BASE_DIR, "landing.html")


# ---------------------------------------------------------------------
# Public page-content API (used by about.html, careers.html, etc.)
# ---------------------------------------------------------------------
@app.route("/api/pages/<key>", methods=["GET"])
def api_get_page(key):
    page = get_page(key)
    if not page:
        return jsonify({"error": "Page not found."}), 404
    return jsonify({"key": key, "title": page.get("title", ""), "body": page.get("body", "")}), 200


# ---------------------------------------------------------------------
# Public songs list (for the future user-facing player)
# ---------------------------------------------------------------------
@app.route("/api/songs", methods=["GET"])
def api_songs():
    songs = [r for r in read_records() if r.get("type") == "song"]
    return jsonify({"songs": songs}), 200


# ---------------------------------------------------------------------
# User auth API
# ---------------------------------------------------------------------
@app.route("/api/signup", methods=["POST"])
def api_signup():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""

    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are all required."}), 400
    if find_user(username):
        return jsonify({"error": "That username is already taken."}), 409

    append_record({
        "type": "user",
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
    })
    return jsonify({"message": "Account created! You can now log in."}), 201


@app.route("/api/login", methods=["POST"])
def api_login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    user = find_user(username)
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        return jsonify({"error": "Invalid username or password."}), 401
    return jsonify({"message": f"Welcome back, {username}!"}), 200


# ---------------------------------------------------------------------
# Admin auth API
# ---------------------------------------------------------------------
@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    admin = find_admin(username)
    if not admin or not check_password_hash(admin.get("password_hash", ""), password):
        return jsonify({"error": "Invalid admin username or password."}), 401

    token = uuid.uuid4().hex
    ADMIN_SESSIONS[token] = username
    return jsonify({"message": "Welcome, admin.", "token": token}), 200


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        ADMIN_SESSIONS.pop(auth.split(" ", 1)[1], None)
    return jsonify({"message": "Logged out."}), 200


# ---------------------------------------------------------------------
# Admin: edit page content
# ---------------------------------------------------------------------
@app.route("/api/admin/pages", methods=["GET"])
def api_admin_list_pages():
    if not require_admin():
        return jsonify({"error": "Unauthorized."}), 401
    pages = [r for r in read_records() if r.get("type") == "page"]
    return jsonify({"pages": pages}), 200


@app.route("/api/admin/pages/<key>", methods=["POST"])
def api_admin_update_page(key):
    if not require_admin():
        return jsonify({"error": "Unauthorized."}), 401
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    if not title or not body:
        return jsonify({"error": "Title and body are both required."}), 400
    upsert_page(key, title, body)
    return jsonify({"message": "Page updated."}), 200


# ---------------------------------------------------------------------
# Admin: upload music (name, description, cover image, audio file)
# ---------------------------------------------------------------------
ALLOWED_AUDIO_EXT = {"mp3", "wav", "ogg", "m4a"}
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}


def ext_of(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


@app.route("/api/admin/upload-music", methods=["POST"])
def api_admin_upload_music():
    if not require_admin():
        return jsonify({"error": "Unauthorized."}), 401

    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    audio_file = request.files.get("audio")
    cover_file = request.files.get("cover")

    if not name or not audio_file:
        return jsonify({"error": "Song name and an audio file are required."}), 400

    audio_ext = ext_of(audio_file.filename)
    if audio_ext not in ALLOWED_AUDIO_EXT:
        return jsonify({"error": "Unsupported audio format."}), 400

    song_id = uuid.uuid4().hex[:12]
    audio_filename = f"song_{song_id}.{audio_ext}"
    audio_file.save(os.path.join(BASE_DIR, secure_filename(audio_filename)))

    cover_filename = ""
    if cover_file and cover_file.filename:
        cover_ext = ext_of(cover_file.filename)
        if cover_ext in ALLOWED_IMAGE_EXT:
            cover_filename = f"cover_{song_id}.{cover_ext}"
            cover_file.save(os.path.join(BASE_DIR, secure_filename(cover_filename)))

    append_record({
        "type": "song",
        "id": song_id,
        "name": name,
        "description": description,
        "audio_filename": audio_filename,
        "cover_filename": cover_filename,
    })
    return jsonify({"message": "Song uploaded.", "id": song_id}), 201


@app.route("/api/admin/songs", methods=["GET"])
def api_admin_songs():
    if not require_admin():
        return jsonify({"error": "Unauthorized."}), 401
    songs = [r for r in read_records() if r.get("type") == "song"]
    return jsonify({"songs": songs}), 200


@app.route("/api/admin/songs/<song_id>", methods=["DELETE"])
def api_admin_delete_song(song_id):
    if not require_admin():
        return jsonify({"error": "Unauthorized."}), 401

    records = read_records()
    target = None
    remaining = []
    for rec in records:
        if rec.get("type") == "song" and rec.get("id") == song_id:
            target = rec
        else:
            remaining.append(rec)

    if not target:
        return jsonify({"error": "Song not found."}), 404

    for fname_key in ("audio_filename", "cover_filename"):
        fname = target.get(fname_key)
        if fname:
            fpath = os.path.join(BASE_DIR, fname)
            if os.path.exists(fpath):
                os.remove(fpath)

    write_records(remaining)
    return jsonify({"message": "Song deleted."}), 200


# ---------------------------------------------------------------------
# Admin: manage users
# ---------------------------------------------------------------------
@app.route("/api/admin/users", methods=["GET"])
def api_admin_list_users():
    if not require_admin():
        return jsonify({"error": "Unauthorized."}), 401
    users = [
        {"username": r.get("username"), "email": r.get("email")}
        for r in read_records() if r.get("type") == "user"
    ]
    return jsonify({"users": users}), 200


@app.route("/api/admin/users/<username>", methods=["DELETE"])
def api_admin_delete_user(username):
    if not require_admin():
        return jsonify({"error": "Unauthorized."}), 401

    records = read_records()
    target = None
    remaining = []
    for rec in records:
        if rec.get("type") == "user" and rec.get("username") == username:
            target = rec
        else:
            remaining.append(rec)

    if not target:
        return jsonify({"error": "User not found."}), 404

    write_records(remaining)
    return jsonify({"message": "User deleted."}), 200


# ---------------------------------------------------------------------
# Admin: change own password
# ---------------------------------------------------------------------
@app.route("/api/admin/change-password", methods=["POST"])
def api_admin_change_password():
    username = require_admin()
    if not username:
        return jsonify({"error": "Unauthorized."}), 401

    payload = request.get_json(silent=True) or {}
    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""

    admin = find_admin(username)
    if not admin or not check_password_hash(admin.get("password_hash", ""), current_password):
        return jsonify({"error": "Current password is incorrect."}), 401
    if not new_password or len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters."}), 400

    records = read_records()
    for rec in records:
        if rec.get("type") == "admin" and rec.get("username") == username:
            rec["password_hash"] = generate_password_hash(new_password)
            break
    write_records(records)
    return jsonify({"message": "Password updated."}), 200


# ---------------------------------------------------------------------
# Admin: dashboard summary counts
# ---------------------------------------------------------------------
@app.route("/api/admin/stats", methods=["GET"])
def api_admin_stats():
    if not require_admin():
        return jsonify({"error": "Unauthorized."}), 401
    records = read_records()
    return jsonify({
        "users": sum(1 for r in records if r.get("type") == "user"),
        "songs": sum(1 for r in records if r.get("type") == "song"),
        "pages": sum(1 for r in records if r.get("type") == "page"),
    }), 200


# ---------------------------------------------------------------------
# Admin panel page
# ---------------------------------------------------------------------
@app.route("/admin")
def admin_panel():
    return send_from_directory(BASE_DIR, "admin.html")


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------
if __name__ == "__main__":
    init_data_file()
    init_defaults()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
else:
    init_data_file()
    init_defaults()

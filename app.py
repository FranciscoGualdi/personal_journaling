"""
Daily Questions - answer a set of questions by voice, save the transcript to Google Drive.
Quick notes can be added during the day; they are kept locally and merged into the
day's file when the answers are saved.

Run:  uv run app.py   then open http://localhost:5000 in Chrome or Edge.
"""
import datetime
import json
import os
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"   # OAuth client downloaded from Google Cloud
TOKEN_FILE = BASE_DIR / "token.json"               # created automatically after first login
LOCAL_DIR = BASE_DIR / "answers"                   # local backup copy of every save
DRIVE_FOLDER_NAME = os.environ.get("DRIVE_FOLDER_NAME", "Daily Answers")
FILE_PREFIX = "daily-answers"
NOTES_PREFIX = "notes"                             # local-only notes, merged into the daily file on save

# drive.file = the app can only see/edit files it created itself (least privilege)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

app = Flask(__name__)
notes_lock = threading.Lock()


# ---------------------------------------------------------------- Google Drive
def get_drive_service():
    """Return an authorized Drive client, or None if credentials.json is missing."""
    if not CREDENTIALS_FILE.exists():
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None  # refresh token revoked/expired -> log in again
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _q(value: str) -> str:
    """Escape a value for a Drive search query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_one(service, query):
    res = service.files().list(q=query, spaces="drive", fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def _folder_id(service):
    query = (f"name = '{_q(DRIVE_FOLDER_NAME)}' and "
             "mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    folder_id = _find_one(service, query)
    if folder_id:
        return folder_id
    meta = {"name": DRIVE_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
    return service.files().create(body=meta, fields="id").execute()["id"]


def upload_to_drive(service, filename, text):
    """Create the day's file, or overwrite it if it already exists."""
    from googleapiclient.http import MediaInMemoryUpload

    folder_id = _folder_id(service)
    media = MediaInMemoryUpload(text.encode("utf-8"), mimetype="text/plain", resumable=False)
    existing = _find_one(service, f"name = '{_q(filename)}' and '{folder_id}' in parents and trashed = false")
    if existing:
        return service.files().update(fileId=existing, media_body=media,
                                      fields="id,webViewLink").execute()
    meta = {"name": filename, "parents": [folder_id]}
    return service.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()


# ---------------------------------------------------------------- helpers
def today_str():
    return datetime.date.today().isoformat()


def filename_for(day):
    return f"{FILE_PREFIX}-{day}.txt"


def notes_path(day):
    return LOCAL_DIR / f"{NOTES_PREFIX}-{day}.json"


def load_notes(day):
    path = notes_path(day)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def write_notes(day, notes):
    LOCAL_DIR.mkdir(exist_ok=True)
    tmp = notes_path(day).with_suffix(".tmp")
    tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(notes_path(day))  # atomic, so a crash never leaves a half-written file


def build_text(day, answers, notes):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"Daily answers - {day}", f"Saved: {now}", ""]
    for i, item in enumerate(answers, start=1):
        lines.append(f"Q{i}. {item.get('question', '').strip()}")
        lines.append(f"A: {item.get('answer', '').strip() or '(no answer)'}")
        lines.append("")
    if notes:
        lines.append("Notes during the day")
        for note in notes:
            lines.append(f"[{note['time']}] {note['text']}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- routes
@app.get("/")
def index():
    day = today_str()
    already_saved = (LOCAL_DIR / filename_for(day)).exists()
    return render_template("index.html", today=day, already_saved=already_saved)


@app.get("/notes")
def list_notes():
    return jsonify(notes=load_notes(today_str()))


@app.post("/notes")
def add_note():
    text = ((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not text:
        return jsonify(ok=False, error="The note is empty."), 400
    note = {"id": uuid.uuid4().hex, "time": datetime.datetime.now().strftime("%H:%M"),
            "text": text, "consolidated": False}
    day = today_str()
    with notes_lock:
        notes = load_notes(day)
        notes.append(note)
        write_notes(day, notes)
    return jsonify(ok=True, note=note)


@app.delete("/notes/<note_id>")
def delete_note(note_id):
    day = today_str()
    with notes_lock:
        notes = load_notes(day)
        write_notes(day, [n for n in notes if n["id"] != note_id])
    return jsonify(ok=True)


@app.post("/save")
def save():
    data = request.get_json(silent=True) or {}
    answers = data.get("answers") or []
    day = today_str()
    with notes_lock:
        notes = load_notes(day)
    if not notes and not any((a.get("answer") or "").strip() for a in answers):
        return jsonify(ok=False, error="Nothing to save - answer a question or add a note."), 400

    filename = filename_for(day)
    text = build_text(day, answers, notes)

    # 1) always keep a local copy
    LOCAL_DIR.mkdir(exist_ok=True)
    (LOCAL_DIR / filename).write_text(text, encoding="utf-8")

    # mark the merged notes so the page can show which ones are still pending
    saved_ids = {n["id"] for n in notes}
    with notes_lock:
        current = load_notes(day)
        for n in current:
            if n["id"] in saved_ids:
                n["consolidated"] = True
        write_notes(day, current)

    # 2) upload to Google Drive
    result = {"ok": True, "filename": filename, "local": True, "drive": False}
    try:
        service = get_drive_service()
        if service is None:
            result["drive_error"] = "credentials.json not found - saved locally only."
        else:
            f = upload_to_drive(service, filename, text)
            result.update(drive=True, link=f.get("webViewLink"))
    except Exception as exc:  # keep the local save even if Drive fails
        result["drive_error"] = f"Drive upload failed: {exc}"
    return jsonify(result)


if __name__ == "__main__":
    if CREDENTIALS_FILE.exists():
        print("Checking Google Drive authorization...")
        get_drive_service()  # first run opens a browser window to log in
        print("Google Drive ready.")
    else:
        print("credentials.json not found: answers will be saved locally only (see README).")
    app.run(host="127.0.0.1", port=5000, debug=False)

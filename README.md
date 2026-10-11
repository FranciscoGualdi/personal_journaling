# Daily Questions

A small journaling app that runs on your own computer. During the day you jot down quick notes by
voice or by typing. In the evening you answer a few fixed questions the same way. When you save,
everything from that day goes into one text file, which is kept locally and uploaded to Google Drive.

## How it works

### Your day with the app

1. **During the day: add notes.** Open the page, press **🎤 Speak** in the *Notes during the day* box
   and talk, then press **⏹ Stop & add**. Or type the note and press **Add note**. The note gets the current time (e.g. `14:32`) and is written
   straight to a file on your computer. Nothing goes to Google Drive yet. Add as many notes as you like.
   You can close the browser between notes, because they're stored on disk, not in the page.
2. **In the evening: answer the questions.** Each question has its own mic button. Speak, stop, and fix the
   text by hand if the transcription got something wrong. Unsaved answers are kept in the browser as a
   draft, so refreshing the page doesn't lose them.
3. **Save the day.** **Save today's journal** combines your answers and all of today's notes into one
   text file. It saves that file locally and uploads it to Drive. Each note is then marked *saved*.
   If you add a note afterwards, it shows *not saved yet*. Save again to include it; today's file
   is overwritten with the full, updated version.

### What gets saved where

| What | Where | When |
|---|---|---|
| Answers you haven't saved yet | Your browser (`localStorage`) | As you type or speak |
| Notes | `answers/notes-YYYY-MM-DD.json` on your computer | Immediately, when you press **Add note** |
| The day's journal | `answers/daily-answers-YYYY-MM-DD.txt` on your computer | When you press **Save today's journal** |
| The same journal file | **Daily Answers** folder in Google Drive | Right after the local save |

The local copy is always written first, so if Drive is unreachable or `credentials.json` is missing,
nothing is lost. The page tells you the file was only saved locally.

"Today" means your computer's date when you add the note or save. A note added after midnight
belongs to the next day.

### What the saved file looks like

```text
Daily answers - 2026-10-11
Saved: 2026-10-11 21:40

Q1. How am I feeling mentally, physically, and emotionally today?
A: Tired but calm. Good energy in the morning, dipped after lunch.

Q2. What are three small things I am genuinely grateful for today?
A: The walk to the station, a call with my sister, a quiet evening.

Q3. What could you have done better?
A: Started the hard task earlier instead of answering emails first.

Notes during the day
[09:14] Idea: try doing the questions right after dinner instead of before bed.
[14:32] Meeting went better than expected.
```

### Under the hood

```
 Browser (Chrome / Edge)                     app.py (Flask, localhost:5000)        Google Drive
 ┌───────────────────────────┐   HTTP     ┌───────────────────────────────┐  API  ┌──────────────┐
 │ templates/index.html      │ ─────────► │ /notes  add / list / delete   │       │ Daily Answers│
 │ • speech → text (Web      │            │ /save   build the day's file, │ ────► │  folder      │
 │   Speech API)             │ ◄───────── │         write it locally,     │       └──────────────┘
 │ • drafts in localStorage  │            │         upload it to Drive    │
 └───────────────────────────┘            └──────────────┬────────────────┘
                                                         ▼
                                                  answers/ folder
```

- **Speech to text happens in the browser**, using its built-in Web Speech API. The server only ever
  receives text. That's why Chrome or Edge is required, and why the speech language picker is on the page.
- **The Flask server** (`app.py`) serves the page, stores notes, builds the daily text file and
  uploads it. It only listens on `127.0.0.1`, so other devices on your network can't reach it
  (to use it from your phone, see [setup step 4](#4-use-it-from-your-phone-optional-with-tailscale)).
- **Google Drive access** uses OAuth with the narrow `drive.file` permission. The app can see only the
  folder and files it created itself, not the rest of your Drive.

```
personal_journaling/
├── app.py               # Flask server: notes, saving, Google Drive upload
├── templates/index.html # the page: questions, notes, speech recognition
├── pyproject.toml       # dependencies (managed by uv)
├── uv.lock
├── credentials.json     # you add this (setup step 2), keep it private
├── token.json           # created after your first Google login, keep it private
└── answers/             # created automatically: notes and daily journal files
```

> `credentials.json`, `token.json` and `answers/` contain secrets or personal writing. Add them to
> `.gitignore` before pushing this project anywhere.

## Setup

### 1. Install

Install [uv](https://docs.astral.sh/uv/), then in this folder:

```bash
uv sync
```

This creates `.venv` with the right Python version and the locked dependencies.
To add a dependency later: `uv add <package>`.

### 2. Connect Google Drive (one-time, optional)

Skip this if you only want local files; the app works without it.

1. Go to <https://console.cloud.google.com/> and create a project (e.g. "Daily Questions").
2. **APIs & Services → Library** → enable **Google Drive API**.
3. **APIs & Services → OAuth consent screen** → User type *External* → fill in the app name and your email
   → add yourself under **Test users**.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type **Desktop app**.
5. Download the JSON, rename it to `credentials.json` and put it next to `app.py`.

> While the consent screen is in **Testing** mode, Google expires the login after about 7 days. If saving
> to Drive starts failing, delete `token.json` and restart the app to log in again. Alternatively, set the
> consent screen's publishing status to **In production**. For personal use with this limited permission,
> you don't need to submit it for verification.

### 3. Run

```bash
uv run app.py
```

The first time, a browser window opens to log in to Google; afterwards `token.json` keeps you logged in.
Then open **http://localhost:5000** in **Chrome or Edge** and allow microphone access.
Firefox and Safari don't support the speech recognition used here, but you can still type.

### 4. Use it from your phone (optional, with Tailscale)

Two things stop the phone from simply connecting to your computer. The app only accepts connections
from the computer itself. And browsers only allow the microphone on secure (`https://`) pages, apart
from `localhost`, so plain `http://192.168.x.x:5000` over Wi-Fi would load but the mic wouldn't work.

[Tailscale](https://tailscale.com) solves both without any change to the app. It's a free private
network between your own devices. Its `serve` command gives your computer an `https://` address that
only your devices can open, and passes requests on to the app on `localhost`. Your journal is never
on the public internet.

1. Install Tailscale on your computer and your phone, and sign in with the same account on both.
2. In the [Tailscale admin console](https://login.tailscale.com/admin/dns), turn on **MagicDNS** and
   **HTTPS Certificates**.
3. Start the app on the computer as usual: `uv run app.py`.
4. In a second terminal, run:

   ```bash
   tailscale serve --bg 5000
   ```

   It prints your address, something like `https://your-pc.your-tailnet.ts.net`. The `--bg` flag keeps
   it running in the background, even after restarts. To stop sharing: `tailscale serve --https=443 off`.
5. On the phone, make sure Tailscale is connected. Open the address in **Chrome** (Android) or
   **Safari** (iPhone) and allow microphone access.
6. Optional: use the browser's **Add to Home Screen** so it opens like an app.

Good to know:

- **Your computer must be on and awake** (and the app running) for the phone to connect. Set Windows not to
  sleep while plugged in if you want to use it during the day.
- **Unsaved answers stay in the browser you typed them in.** Notes and saved journals live on the computer,
  so the phone and the computer show the same ones.
- **Speech recognition works best in Chrome on Android.** Safari on iPhone supports it but is less reliable.
  Typing always works.
- **Don't change the app to listen on `0.0.0.0`, or use a public tunnel** such as ngrok, as a shortcut.
  The app has no password, so anyone on your Wi-Fi or on the internet could read your journal.

## Tips

- **Speech language**: pick it at the top of the page (English, Portuguese, Dutch). The choice is remembered.
- **⏹ Stop & add** on the notes mic adds the note straight away. No need to press **Add note**.
  For typed notes, **Ctrl+Enter** in the note box adds the note.
- If the note box still has text when you press **Save today's journal**, it's added as a note first.
- **Delete** removes a note. If the note was already saved, save again to remove it from the journal file.
- **Drive folder name**: set the `DRIVE_FOLDER_NAME` environment variable (default: `Daily Answers`).

## Customizing

- **Questions**: edit the `QUESTIONS` list near the top of the `<script>` in `templates/index.html`.
- **More speech languages**: add an `<option>` with a language code (e.g. `de-DE`) to the
  `<select id="lang">` in the same file.

## Privacy note

Your notes and answers are stored as plain files on your computer and in your own Google Drive.
The one thing that leaves your machine during use is the **audio**. In Chrome and Edge, the Web
Speech API sends it to Google's or Microsoft's speech service to be transcribed. If you want everything
to stay local, the next step would be to record audio in the page and transcribe it in Python with
a local model such as Whisper (`faster-whisper`).

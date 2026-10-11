"""
בוט תמלול בטלגרם
מעבירים לבוט הודעה קולית (גם מוואטסאפ דרך "שיתוף") -> הוא מחזיר תמלול בעברית.
Telegram Bot API + Whisper דרך Groq (חינם). רץ על Render.
"""
import os
import hashlib
import logging
import threading

import requests
from flask import Flask, request
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("transcriber")

# ---------- הגדרות (משתני סביבה ב-Render) ----------
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]            # מ-BotFather
TRANSCRIBE_API_KEY = os.environ.get("TRANSCRIBE_API_KEY") or os.environ["GROQ_API_KEY"]
TRANSCRIBE_BASE_URL = os.environ.get("TRANSCRIBE_BASE_URL", "https://api.groq.com/openai/v1")
TRANSCRIBE_MODEL = os.environ.get("TRANSCRIBE_MODEL", "whisper-large-v3")
LANGUAGE = os.environ.get("LANGUAGE", "he")
# מזהי טלגרם מורשים, מופרדים בפסיק. ריק = כולם יכולים להשתמש
ALLOWED_USERS = {u.strip() for u in os.environ.get("ALLOWED_USERS", "").split(",") if u.strip()}
# Render ממלא את זה אוטומטית
PUBLIC_URL = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"
SECRET = hashlib.sha256(TELEGRAM_TOKEN.encode()).hexdigest()[:32]  # מוודא שהבקשות באמת מטלגרם

app = Flask(__name__)
client = OpenAI(api_key=TRANSCRIBE_API_KEY, base_url=TRANSCRIBE_BASE_URL)
seen_updates = set()


# ---------- טלגרם ----------
def send_text(chat_id, text, reply_to=None):
    for i in range(0, max(len(text), 1), 4000):
        payload = {"chat_id": chat_id, "text": text[i:i + 4000]}
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=30)
        if r.status_code >= 400:
            log.error("send failed: %s %s", r.status_code, r.text)


def send_typing(chat_id):
    try:
        requests.post(f"{API}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except Exception:
        pass


def download_file(file_id):
    info = requests.get(f"{API}/getFile", params={"file_id": file_id}, timeout=30).json()
    if not info.get("ok"):
        raise RuntimeError(f"getFile failed: {info}")
    path = info["result"]["file_path"]
    data = requests.get(f"{FILE_API}/{path}", timeout=120)
    data.raise_for_status()
    return data.content, path


def find_audio(msg):
    """מחזיר (file_id, שם קובץ) אם בהודעה יש אודיו, אחרת None"""
    if "voice" in msg:
        return msg["voice"]["file_id"], "voice.ogg"
    if "audio" in msg:
        return msg["audio"]["file_id"], msg["audio"].get("file_name") or "audio.mp3"
    if "video_note" in msg:
        return msg["video_note"]["file_id"], "video.mp4"
    if "video" in msg:
        return msg["video"]["file_id"], msg["video"].get("file_name") or "video.mp4"
    doc = msg.get("document")
    if doc:
        mime = doc.get("mime_type", "")
        name = doc.get("file_name") or "file"
        if mime.startswith(("audio/", "video/")) or name.lower().endswith(
                (".opus", ".ogg", ".mp3", ".m4a", ".wav", ".aac", ".amr", ".mp4", ".webm")):
            return doc["file_id"], name
    return None


# ---------- תמלול ----------
AUDIO_EXT = (".ogg", ".mp3", ".m4a", ".wav", ".mp4", ".webm", ".flac", ".mpeg", ".mpga")


def transcribe(data, filename):
    name = filename.lower()
    if name.endswith(".opus"):
        name = name[:-5] + ".ogg"         # Whisper מכיר opus בתור ogg
    elif not name.endswith(AUDIO_EXT):
        name = "audio.ogg"
    result = client.audio.transcriptions.create(
        model=TRANSCRIBE_MODEL, file=(name, data), language=LANGUAGE)
    return result.text.strip()


def handle_audio(chat_id, msg_id, file_id, filename):
    try:
        send_typing(chat_id)
        data, path = download_file(file_id)
        text = transcribe(data, filename if "." in filename else path)
        send_text(chat_id, f"📝 {text}" if text else "לא זוהה דיבור בהקלטה.", reply_to=msg_id)
    except Exception:
        log.exception("transcription failed")
        send_text(chat_id, "משהו השתבש בתמלול, נסי לשלוח שוב 🙏", reply_to=msg_id)


# ---------- Webhook ----------
@app.post("/telegram")
def telegram_webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
        return "forbidden", 403
    update = request.get_json(silent=True) or {}
    uid = update.get("update_id")
    if uid in seen_updates:
        return "ok"
    seen_updates.add(uid)

    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return "ok"
    chat_id = msg["chat"]["id"]
    user_id = str((msg.get("from") or {}).get("id", chat_id))

    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        send_text(chat_id, f"אין לך הרשאה לבוט הזה. (המזהה שלך: {user_id})")
        return "ok"

    audio = find_audio(msg)
    if audio:
        threading.Thread(target=handle_audio, args=(chat_id, msg["message_id"], *audio), daemon=True).start()
    else:
        send_text(chat_id,
                  "היי! שלחי או העבירי לי הודעה קולית ואחזיר לך תמלול 🎙️\n"
                  f"המזהה שלך בטלגרם: {user_id}")
    return "ok"


def register_webhook():
    if not PUBLIC_URL:
        log.warning("no PUBLIC_URL / RENDER_EXTERNAL_URL – webhook not registered")
        return
    url = PUBLIC_URL.rstrip("/") + "/telegram"
    r = requests.post(f"{API}/setWebhook", json={
        "url": url, "secret_token": SECRET,
        "allowed_updates": ["message"], "drop_pending_updates": False,
    }, timeout=30)
    log.info("setWebhook %s -> %s", url, r.text)


@app.get("/")
def health():
    return "Transcriber bot is running", 200


try:
    register_webhook()
except Exception:
    log.exception("webhook registration failed")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

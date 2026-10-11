"""
בוט תמלול לוואטסאפ
מעבירים לבוט הודעה קולית -> הוא מחזיר תמלול בעברית.
WhatsApp Cloud API (רשמי) + Whisper דרך Groq (חינם). מתאים ל-Render / Railway.
"""
import os
import threading
import logging

import requests
from flask import Flask, request
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("transcriber")

# ---------- הגדרות (משתני סביבה ב-Railway) ----------
WHATSAPP_TOKEN = os.environ["WHATSAPP_TOKEN"]          # טוקן קבוע מ-Meta
PHONE_NUMBER_ID = os.environ["PHONE_NUMBER_ID"]        # מזהה המספר של הבוט
VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]              # מילה סודית שאת בוחרת
# ברירת מחדל: Groq (שכבה חינמית). לעבור ל-OpenAI: TRANSCRIBE_BASE_URL=https://api.openai.com/v1
# ו-TRANSCRIBE_MODEL=gpt-4o-transcribe
TRANSCRIBE_API_KEY = os.environ.get("TRANSCRIBE_API_KEY") or os.environ["GROQ_API_KEY"]
TRANSCRIBE_BASE_URL = os.environ.get("TRANSCRIBE_BASE_URL", "https://api.groq.com/openai/v1")
TRANSCRIBE_MODEL = os.environ.get("TRANSCRIBE_MODEL", "whisper-large-v3")
LANGUAGE = os.environ.get("LANGUAGE", "he")
# רק המספרים האלה יכולים להשתמש בבוט (פורמט בינלאומי בלי +, למשל 972501234567)
ALLOWED_NUMBERS = {n.strip() for n in os.environ.get("ALLOWED_NUMBERS", "").split(",") if n.strip()}
GRAPH = "https://graph.facebook.com/v21.0"

app = Flask(__name__)
openai_client = OpenAI(api_key=TRANSCRIBE_API_KEY, base_url=TRANSCRIBE_BASE_URL)
seen_ids = set()  # מונע תמלול כפול כש-Meta שולחת שוב את אותה הודעה


# ---------- וואטסאפ ----------
def wa_headers():
    return {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}


def send_text(to, body, reply_to=None):
    # וואטסאפ מגביל ל-4096 תווים להודעה, מפצלים אם צריך
    chunks = [body[i:i + 4000] for i in range(0, len(body), 4000)] or [""]
    for chunk in chunks:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": chunk},
        }
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        r = requests.post(f"{GRAPH}/{PHONE_NUMBER_ID}/messages",
                          headers=wa_headers(), json=payload, timeout=30)
        if r.status_code >= 400:
            log.error("send failed: %s %s", r.status_code, r.text)


def download_media(media_id):
    meta = requests.get(f"{GRAPH}/{media_id}", headers=wa_headers(), timeout=30)
    meta.raise_for_status()
    info = meta.json()
    audio = requests.get(info["url"], headers=wa_headers(), timeout=120)
    audio.raise_for_status()
    mime = info.get("mime_type", "audio/ogg")
    return audio.content, mime


# ---------- תמלול ----------
EXT = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
       "audio/aac": "m4a", "audio/amr": "amr", "audio/wav": "wav", "audio/webm": "webm"}


def transcribe(data, mime):
    ext = EXT.get(mime.split(";")[0].strip(), "ogg")
    result = openai_client.audio.transcriptions.create(
        model=TRANSCRIBE_MODEL,
        file=(f"voice.{ext}", data),
        language=LANGUAGE,
    )
    return result.text.strip()


def handle_audio(sender, msg_id, media_id):
    try:
        data, mime = download_media(media_id)
        text = transcribe(data, mime)
        send_text(sender, f"📝 תמלול:\n\n{text}" if text else "לא זוהה דיבור בהקלטה.", reply_to=msg_id)
    except Exception as e:
        log.exception("transcription failed")
        send_text(sender, "משהו השתבש בתמלול, נסי לשלוח שוב 🙏", reply_to=msg_id)


# ---------- Webhook ----------
@app.get("/webhook")
def verify():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == VERIFY_TOKEN):
        return request.args.get("hub.challenge", ""), 200
    return "forbidden", 403


@app.post("/webhook")
def incoming():
    body = request.get_json(silent=True) or {}
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                msg_id, sender, mtype = msg.get("id"), msg.get("from"), msg.get("type")
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
                if ALLOWED_NUMBERS and sender not in ALLOWED_NUMBERS:
                    continue
                if mtype == "audio":
                    # עונים ל-Meta מיד ומתמללים ברקע
                    threading.Thread(target=handle_audio,
                                     args=(sender, msg_id, msg["audio"]["id"]),
                                     daemon=True).start()
                else:
                    send_text(sender, "שלחי או העבירי לי הודעה קולית ואחזיר לך תמלול 🎙️", reply_to=msg_id)
    return "ok", 200


PRIVACY_HTML = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>מדיניות פרטיות</title>
<style>body{font-family:Arial,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.7}</style>
</head><body><h1>מדיניות פרטיות – בוט תמלול</h1>
<p>הבוט הוא כלי אישי לתמלול הודעות קוליות שנשלחות אליו בוואטסאפ.</p>
<ul>
<li>הבוט מקבל רק הודעות שנשלחות אליו ישירות, ופועל רק עבור מספרים מורשים.</li>
<li>ההקלטה נשלחת לשירות תמלול (Groq) לצורך המרה לטקסט בלבד, והתמלול נשלח בחזרה לשולח.</li>
<li>הבוט אינו שומר הקלטות או תמלולים, ואינו משתף מידע עם צד שלישי מעבר לכך.</li>
<li>למחיקת מידע או לשאלות: mayy19999@gmail.com</li>
</ul></body></html>"""


@app.get("/privacy")
def privacy():
    return PRIVACY_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/")
def health():
    return "WhatsApp transcriber is running", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# בוט תמלול בטלגרם (חינם)

מעבירים לבוט הודעה קולית ← מקבלים תמלול בעברית.
עובד גם עם הקלטות מוואטסאפ: לחיצה ארוכה על ההקלטה ← העברה ← שיתוף ← טלגרם ← הבוט.

## משתני סביבה ב-Render
| משתנה | ערך |
|---|---|
| `TELEGRAM_TOKEN` | הטוקן מ-BotFather |
| `GROQ_API_KEY` | המפתח מ-Groq |
| `ALLOWED_USERS` | המזהה שלך בטלגרם (הבוט שולח אותו כשכותבים לו) |

ה-Webhook נרשם אוטומטית בכל הפעלה של השרת.

## הרצה ב-Render
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:$PORT`
- Instance: Free (השרת נרדם אחרי ~15 דקות בלי שימוש; ההודעה הראשונה אחרי הפסקה לוקחת עד דקה)

## שדרוג לדיוק מקסימלי (בתשלום)
`TRANSCRIBE_API_KEY` = מפתח OpenAI, `TRANSCRIBE_BASE_URL` = `https://api.openai.com/v1`, `TRANSCRIBE_MODEL` = `gpt-4o-transcribe`

# FamilyText Calendar

SMS-driven family calendar management. Text a natural language message to your Twilio number and it gets added to your shared Google Calendar. No app required.

## Stack
- **Backend**: Python 3.11+ / FastAPI / Railway
- **SMS**: Twilio
- **AI Parsing**: Claude Haiku (Anthropic)
- **Calendar**: Google Calendar API
- **Scheduler**: APScheduler (daily summary at 7:30 AM Central)

---

## Local Development Setup

### 1. Clone and create virtual environment
```powershell
git clone https://github.com/<your-username>/familytext-calendar.git
cd familytext-calendar
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure environment
```powershell
copy .env.example .env
```
Fill in all values in `.env`. Set `ENV=development` for local dev.

### 3. Google OAuth setup (one-time, manual — ~15 minutes)

See **Section 8.3** below.

### 4. Run the development server
```powershell
uvicorn app.main:app --reload --port 8000
```
Health check: `GET http://localhost:8000/health`

### 5. Expose to Twilio (for live testing)
```powershell
winget install ngrok
ngrok http 8000
```
Copy the HTTPS URL and set it as your Twilio webhook: `https://abc123.ngrok.io/webhook/twilio`

---

## Section 8.3 — Google OAuth Setup

> **Manual steps required. Expected time: 15–20 minutes.**

1. Go to [console.cloud.google.com](https://console.cloud.google.com) — sign in with your **family** Google account
2. Create a new project: **FamilyText Calendar**
3. Enable **Google Calendar API** (APIs & Services → Library → search → Enable)
4. Configure OAuth consent screen (APIs & Services → OAuth consent screen):
   - User type: External
   - App name: FamilyText Calendar
   - Add your personal Google account as a **Test user**
5. Create OAuth credentials (APIs & Services → Credentials → + Create → OAuth client ID):
   - Application type: **Desktop app**
   - Name: FamilyText Local
   - Download JSON → save as `credentials.json` in project root
6. Run the auth helper:
   ```powershell
   python scripts/auth.py
   ```
   A browser window opens → sign in → Allow.
   The script prints your `GOOGLE_TOKEN_JSON` and `GOOGLE_CREDENTIALS_JSON` values.
7. Paste those values into Railway environment variables.
8. **Delete** `credentials.json` and `token.json` from your local machine.

### Token refresh monitoring
Google access tokens expire every hour and auto-refresh. When a refresh occurs, the app logs `TOKEN_REFRESHED` with the new token. Update `GOOGLE_TOKEN_JSON` in Railway when you see this. Set a Railway log alert on the string `TOKEN_REFRESHED`.

---

## Railway Deployment

1. Push code to GitHub
2. Railway → New Project → Deploy from GitHub Repo
3. Add all environment variables from `.env.example` (except `ENV` and `SESSION_FILE_PATH`)
4. Railway → Settings → Domains → Generate Domain
5. Set Twilio webhook URL: `https://<your-domain>.up.railway.app/webhook/twilio`
6. Verify: `GET https://<your-domain>.up.railway.app/health` → `{"status":"ok"}`

### Important: Twilio A2P 10DLC
Register your Twilio number for US SMS compliance before announcing the system:
- Twilio Console → Messaging → Regulatory Compliance → Register
- Use case: **Low Volume Mixed**
- Approval takes 1–3 business days. Do not send messages to household users until approved.

### Important: Twilio balance alert
Set an alert at $5 remaining (Twilio Console → Billing → Balance Alerts). Twilio is prepaid — if balance hits $0, messages stop silently with no error.

---

## Known Limitations (V1)

- **No event editing or deletion via SMS** — edit directly in Google Calendar
- **No recurring events** — add recurring events directly in Google Calendar
- **No address resolution** — location stored as plain text exactly as typed
- **No duplicate detection** — sending the same message twice creates two events
- **Token refresh is semi-manual** — see Token refresh monitoring above
- **Search uses exact substring match** — "dentist" matches "Dentist appt" but "dent" does not match "dentist"
- **Session loss on container restart** — an active clarification session is lost if Railway restarts; user must resend their message

---

## Running Tests

```powershell
pytest tests/ -v
```

All 43 tests pass. External APIs (Twilio, Google Calendar, Anthropic) are mocked.

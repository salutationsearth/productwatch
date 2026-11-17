# WatcherMart (ProductWatch) — local demo

Everything runs on your machine:

- WatcherMart web UI (rewards signup, account, manager desk)
- Local webcam aisle interest demo
- Local mock-LLM marketing agent
- Real email send via **Gmail SMTP**

## Setup

```powershell
cd "C:\Users\marsj\OneDrive\Documents\Misc\cursor test\ProductWatch"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python backend/scripts/seed_products.py
```

Edit `.env` and set your Gmail + [App Password](https://myaccount.google.com/apppasswords):

```env
PW_EMAIL_PROVIDER=smtp
PW_SMTP_HOST=smtp.gmail.com
PW_SMTP_PORT=587
PW_SMTP_USERNAME=your.email@gmail.com
PW_SMTP_PASSWORD=xxxx xxxx xxxx xxxx
PW_MARKETING_FROM_EMAIL=your.email@gmail.com
```

## Reset demo data

Stop uvicorn first (SQLite lock), then:

```powershell
python backend/scripts/reset_db.py
```

Wipes users, faces, interest, emails, offers, agent logs, and outbox HTML, then reseeds products/zones/discounts.

## Run

```powershell
uvicorn backend.app.main:app --reload --app-dir .
```

- Store: http://127.0.0.1:8000/
- Rewards signup: http://127.0.0.1:8000/rewards
- Manager: http://127.0.0.1:8000/manager/login (`manager` / `manager`)

## Demo flow

1. Sign up + face scan at `/rewards`
2. Aisle interest (local webcam → local DB):

```powershell
python -m backend.cv.webcam_aisle --user-id 1
```

3. Manager desk → **Run agent now**  
   Agent drafts with the local mock LLM and sends through Gmail SMTP.  
   Terminal prints `===== EMAIL SENT =====` on each send.

## Notes

- Tracking links in emails use `PW_PUBLIC_BASE_URL` (`http://127.0.0.1:8000` by default).
- Outbox HTML copies are still written under `backend/data/outbox/` even when SMTP succeeds.

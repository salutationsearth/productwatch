# ProductWatch

Hackathon product for supermarket aisle interest detection, face-enrolled rewards, and an always-on marketing agent.

Cameras (webcam in this demo) detect when a shopper looks at a product zone. Interest weights + timestamps accumulate in SQLite. A marketing agent emails timely discounts. The marketing desk shows **anonymous** product interest and email funnels only.

## Architecture

```
Browser onboarding → name/email + webcam face frames → face embeddings
Aisle webcam → head/eye gaze → shelf zones → interest weights + timestamps
Marketing agent (loop) → decide/send email → outbox + tracking pixels
Manager dashboard → aggregated interest & conversion (no shopper↔product PII)
```

**CV approach:** OpenCV YuNet/SFace face ID + MediaPipe FaceLandmarker head-pose gaze mapped to shelf zones. No custom gaze net required for the hackathon.

## Stack

- FastAPI + Jinja web UI
- SQLAlchemy + SQLite
- OpenCV + MediaPipe
- Marketing agent with LLM email drafting (`mock` by default; optional OpenAI)
- Email delivery via local outbox, or Resend / SMTP when configured

## Setup (Windows)

```powershell
cd "C:\Users\marsj\OneDrive\Documents\Misc\cursor test\ProductWatch"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python backend/scripts/seed_products.py
uvicorn backend.app.main:app --reload --app-dir .
```

Open:

- Rewards signup: http://127.0.0.1:8000/onboard
- Marketing desk: http://127.0.0.1:8000/dashboard
- API docs: http://127.0.0.1:8000/docs

## Demo flow

### 1. Customer onboarding (web)

1. Go to `/onboard`
2. Enter name + email
3. Allow camera → **Start face scan** (browser captures frames, server stores embedding)

### 2. Aisle interest (desktop CV)

```powershell
python -m backend.cv.webcam_aisle --user-id <id> --seconds 45
```

Aim with your **head** at product boxes. Interest events are timestamped (`first_seen_at` / `last_seen_at` + `interest_events.created_at`).

### 3. Marketing agent

Runs automatically every ~20s while the API is up. It emails when:

- member is face-enrolled with email
- interest weight ≥ threshold
- interest is fresh but not instantaneous (shopper had time to leave)
- user/product cooldowns allow it

Emails land in `backend/data/outbox/*.html` and are tracked via `/t/open`, `/t/click`, `/t/convert`.

Force a demo send after aisle interest (or without waiting):

```powershell
python backend/scripts/demo_interest_and_email.py
```

### LLM email drafting (no paid API required)

By default the agent uses a **mock LLM** with the same prompt → JSON draft contract as a real model (`PW_LLM_PROVIDER=mock`).

When you’re ready for a real model:

```powershell
$env:PW_LLM_PROVIDER="openai"
$env:PW_OPENAI_API_KEY="sk-..."
```

### Actually sending email (free options)

Default is **outbox only** (`backend/data/outbox/*.html`) — fine for demos.

Free / freemium send options:

| Provider | Free tier (approx.) | How to use here |
|----------|---------------------|-----------------|
| **[Resend](https://resend.com)** | ~100 emails/day, 3k/month | Best hackathon fit. Verify a domain or use their onboarding address. |
| **[Brevo](https://www.brevo.com)** | ~300 emails/day | Use SMTP mode with Brevo SMTP credentials |
| **Gmail SMTP** | Personal/demo only | App password + SMTP (easy, not for production volume) |
| **Mailgun / SendGrid** | Trial / limited free | SMTP or their API (not wired; Resend is) |

**Resend (recommended free API):**

```powershell
$env:PW_EMAIL_PROVIDER="resend"
$env:PW_RESEND_API_KEY="re_..."
$env:PW_MARKETING_FROM_EMAIL="onboarding@resend.dev"   # or your verified domain
```

**Gmail SMTP example:**

```powershell
$env:PW_EMAIL_PROVIDER="smtp"
$env:PW_SMTP_HOST="smtp.gmail.com"
$env:PW_SMTP_PORT="587"
$env:PW_SMTP_USERNAME="you@gmail.com"
$env:PW_SMTP_PASSWORD="your-app-password"
$env:PW_MARKETING_FROM_EMAIL="you@gmail.com"
```

Outbox files are always written, even when live send succeeds.

### 4. Marketing desk

`/dashboard` shows:

- KPI strip (members, events, conversion)
- Product interest aggregates (shopper counts / weights — **no names**)
- Email open / click / conversion rates by product
- Agent run log

## Key API routes

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/users` | Create rewards member |
| POST | `/users/{id}/enroll-face-frames` | Browser webcam enrollment |
| GET | `/users/{id}/interests` | Interest weights + timestamps |
| GET | `/analytics/dashboard` | Anonymous aggregates |
| GET | `/agent/status` | Agent heartbeat |
| POST | `/agent/run-once` | Trigger one agent cycle |
| GET | `/t/open/{token}.gif` | Open tracking |
| GET | `/t/click/{token}` | Click tracking |
| GET | `/t/convert/{token}` | Conversion / redeem |

## Privacy note

Face embeddings (not raw photos) are stored for opt-in rewards ID. The marketing dashboard never lists which customer liked which product. Production needs clear consent and biometric compliance — hackathon demo only.

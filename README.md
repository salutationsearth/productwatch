# WatcherMart (ProductWatch)

Hackathon supermarket demo: aisle interest detection, Rewards face enrollment, and an **external OpenAI marketing agent** connected through MCP.

## Architecture

```
WatcherMart web app (FastAPI)
  - Customer: signup, face enroll, my interest
  - Manager: anonymous product interest + emails reported by the agent
  - Tracking links: /t/click /t/convert /t/open

Aisle CV (webcam) → interest weights + timestamps in SQLite

MCP server (stdio) ← OpenAI marketing agent
  list_customer_interests
  create_discount_link
  report_email_sent
  list_sent_emails
  get_link_conversion
```

## Setup

```powershell
cd "C:\Users\marsj\OneDrive\Documents\Misc\cursor test\ProductWatch"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python backend/scripts/seed_products.py
uvicorn backend.app.main:app --reload --app-dir .
```

Storefront:

- http://127.0.0.1:8000/
- Rewards: http://127.0.0.1:8000/rewards
- Account: http://127.0.0.1:8000/account
- Manager: http://127.0.0.1:8000/manager/login (`manager` / `manager`)

## MCP server (for your OpenAI agent)

### Production (VPS)

- Web: `https://productwatch.jacob-yu.com`
- MCP: `https://mcp.productwatch.jacob-yu.com/mcp`

Deploy steps: [deploy/DEPLOY.md](deploy/DEPLOY.md)

Point the OpenAI agent at:

```text
https://mcp.productwatch.jacob-yu.com/mcp
```

If `PW_MCP_AUTH_TOKEN` is set, send header `Authorization: Bearer <token>`.

### Local streamable-http (smoke test)

```powershell
$env:PW_MCP_TRANSPORT="streamable-http"
$env:PW_MCP_HOST="127.0.0.1"
$env:PW_MCP_PORT="8001"
python -m backend.mcp.server
# curl http://127.0.0.1:8001/health
```

### Local stdio

```powershell
$env:PW_MCP_TRANSPORT="stdio"
python -m backend.mcp.server
```

System prompt: [AGENT_SYSTEM_PROMPT.md](AGENT_SYSTEM_PROMPT.md).

### Tool flow

1. `list_customer_interests` → decide who to email  
2. `create_discount_link` → get `claim_url` / `token`  
3. Send the email with your own email channel  
4. `report_email_sent` → appears on the manager dashboard  

## Aisle interest demo

```powershell
python -m backend.cv.webcam_aisle --user-id <id> --seconds 45
```

## Config

Edit `.env` (see `.env.example`). Important:

- `PW_PUBLIC_BASE_URL` — must match the URL customers use so discount links work

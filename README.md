# WatcherMart (ProductWatch)

Hackathon supermarket demo: aisle interest detection, Rewards face enrollment, and an **external OpenAI marketing agent** connected through MCP.

## Architecture

```
Browser (any device) → WatcherMart web
  - Rewards signup + face enroll (browser webcam → server)
  - Customer account / manager dashboard

Your PC (local) → aisle CV demo
  - webcam + gaze locally
  - POST interest to https://productwatch.jacob-yu.com/api/aisle/*

VPS server (no webcam)
  - stores users, embeddings, interest, emails
  - MCP at mcp.productwatch.jacob-yu.com for OpenAI agent
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

## Aisle interest demo (runs on YOUR PC, talks to the server)

1. Sign up + face enroll on the website (`/rewards`).
2. On your computer (venv active, same API key as server `PW_AISLE_API_KEY`):

```powershell
python -m backend.cv.webcam_aisle `
  --server https://productwatch.jacob-yu.com `
  --api-key change-me-aisle-client-key `
  --user-id <id>
```

Omit `--user-id` to face-match against enrollments downloaded from the server.  
Interest events are POSTed to the VPS — the server never opens a webcam.

## Config

Edit `.env` (see `.env.example`). Important:

- `PW_PUBLIC_BASE_URL` — must match the URL customers use so discount links work

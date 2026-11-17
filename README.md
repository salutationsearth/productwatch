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

From the repo root (venv active):

```powershell
python -m backend.mcp.server
```

Point your OpenAI agent / MCP client at that stdio command. Working directory must be the repo root so imports and the SQLite DB resolve correctly.

Example MCP config snippet:

```json
{
  "mcpServers": {
    "watchermart-marketing": {
      "command": "C:\\Users\\marsj\\OneDrive\\Documents\\Misc\\cursor test\\ProductWatch\\.venv\\Scripts\\python.exe",
      "args": ["-m", "backend.mcp.server"],
      "cwd": "C:\\Users\\marsj\\OneDrive\\Documents\\Misc\\cursor test\\ProductWatch"
    }
  }
}
```

System prompt for the agent: see [AGENT_SYSTEM_PROMPT.md](AGENT_SYSTEM_PROMPT.md).

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

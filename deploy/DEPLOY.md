# Deploy WatcherMart on a VPS

## DNS

| Host | Type | Value |
|------|------|--------|
| `productwatch.jacob-yu.com` | A/AAAA | your VPS IP |
| `mcp.productwatch.jacob-yu.com` | A/AAAA | your VPS IP |

## App layout on the server

```bash
sudo mkdir -p /opt/productwatch
sudo chown $USER:$USER /opt/productwatch
# sync/git clone the repo into /opt/productwatch
cd /opt/productwatch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/scripts/seed_products.py
cp .env.example .env
# edit .env — especially PW_PUBLIC_BASE_URL, PW_MCP_*, secrets
```

Recommended `.env` on the VPS:

```env
PW_PUBLIC_BASE_URL=https://productwatch.jacob-yu.com
PW_MCP_TRANSPORT=streamable-http
PW_MCP_HOST=127.0.0.1
PW_MCP_PORT=8001
PW_MCP_PATH=/mcp
PW_MCP_STATELESS_HTTP=true
PW_MCP_PUBLIC_URL=https://mcp.productwatch.jacob-yu.com/mcp
PW_MCP_AUTH_TOKEN=<long-random-secret>
PW_SESSION_SECRET=<another-long-secret>
```

## systemd

```bash
sudo cp deploy/systemd/watchermart-web.service /etc/systemd/system/
sudo cp deploy/systemd/watchermart-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now watchermart-web watchermart-mcp
sudo systemctl status watchermart-web watchermart-mcp
```

## nginx + TLS

```bash
sudo cp deploy/nginx/productwatch.conf /etc/nginx/sites-available/productwatch.conf
sudo ln -sf /etc/nginx/sites-available/productwatch.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d productwatch.jacob-yu.com -d mcp.productwatch.jacob-yu.com
```

## Verify

```bash
curl -s https://productwatch.jacob-yu.com/health
curl -s https://mcp.productwatch.jacob-yu.com/health
# With auth token set:
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer <token>" \
  https://mcp.productwatch.jacob-yu.com/mcp
```

## Point the OpenAI agent at MCP

Remote MCP URL:

```text
https://mcp.productwatch.jacob-yu.com/mcp
```

If you set `PW_MCP_AUTH_TOKEN`, configure the agent/client to send:

```http
Authorization: Bearer <same-token>
```

Use the system prompt in `AGENT_SYSTEM_PROMPT.md`.

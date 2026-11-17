# ProductWatch

Hackathon backend + computer vision for supermarket shelf interest detection and a face-enrolled rewards program.

Cameras (webcam in this demo) detect when a shopper looks at a product zone. Interest weights accumulate in SQLite. Rewards members get personalized discounts on products they stare at — and competitor offers meant to steal share.

## Architecture

```
Webcam → Face enroll (YuNet + SFace embeddings)
Webcam → Aisle loop (MediaPipe head-pose gaze → shelf zones → interest weights)
SQLite → users, products, embeddings, interest, discounts, offers
FastAPI → CRUD + session triggers
```

**CV approach (no custom gaze net):** compose pretrained OpenCV face recognition + MediaPipe Face Mesh head pose, map gaze to calibrated product rectangles, score interest with dwell-time heuristics. That is the right hackathon path; training from scratch needs labeled aisle video you do not have yet.

### Later fine-tune path

1. Export frames + features during aisle sessions (`gaze_x/y`, yaw/pitch, face area, zone id).
2. Label `(features → product_id interested?)` offline.
3. Train a small classifier (logistic / tiny MLP) on those features; swap it in for the dwell heuristic.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy + SQLite
- OpenCV (YuNet detect + SFace embed)
- MediaPipe Tasks FaceLandmarker (head-pose gaze proxy)

## Setup (Windows)

```powershell
cd "C:\Users\marsj\OneDrive\Documents\Misc\cursor test\ProductWatch"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Face models download automatically into `backend/models/` on first enroll/aisle run.

## Demo flow

### 1. Seed catalog + shelf zones

```powershell
python backend/scripts/seed_products.py
```

Zones are rectangles on the webcam preview (`camera_id=webcam-0`).

### 2. Start API (optional for CLI demos)

```powershell
uvicorn backend.app.main:app --reload --app-dir .
```

- Docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

### 3. Create a rewards user

```powershell
curl -X POST http://127.0.0.1:8000/users -H "Content-Type: application/json" -d "{\"name\":\"Jacob\",\"email\":\"jacob@example.com\",\"is_rewards_member\":true}"
```

### 4. Enroll face (webcam window)

```powershell
python -m backend.cv.webcam_enroll 1
```

Or `POST /users/{id}/enroll-face` (opens webcam on the server machine).

### 5. Run aisle interest session

```powershell
python -m backend.cv.webcam_aisle --user-id 1 --seconds 45
```

1. Session opens **fullscreen**. Look at the **center** of the screen for ~0.7s (auto-calibrate). Press `C` to recalibrate, `F` to toggle fullscreen, `Q`/`Esc` to quit.
2. **Aim with your head** toward a product box; eyes only fine-tune near center (iris fades while you turn).
3. Yellow crosshair = gaze cursor. After ~1.5s dwell, interest weight bumps and offers refresh.
4. If left/right still feels inverted: set env `PW_GAZE_X_SIGN=-1` and rerun.

### 6. Inspect interests + offers

```powershell
curl http://127.0.0.1:8000/users/1/interests
curl http://127.0.0.1:8000/users/1/offers
```

## Key API routes

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/users` | Create shopper / rewards member |
| POST | `/users/{id}/enroll-face` | Webcam face enroll |
| GET | `/users/{id}/interests` | Product interest weights |
| GET | `/users/{id}/offers` | Personalized + competitor + member deals |
| POST | `/products` | Add product |
| PUT | `/cameras/{camera_id}/zones` | Replace shelf zone map |
| POST | `/session/aisle/start` | Blocking webcam aisle session |

## Interest + discounts

- **Weight** on `user_product_interest` (0–100), bumped when gaze dwells in a zone.
- **Personalized** offer when weight ≥ 15.
- **Competitor** offer for another product in the same `competitor_group`.
- **Member general** 5% deals for `is_rewards_member=true`.

## Privacy note

Face embeddings (not raw photos) are stored for opt-in rewards ID. For a real supermarket deployment you would need clear consent, retention limits, and local regs (biometric laws). Hackathon demo only.

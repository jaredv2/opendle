# Opendle Backend

A FastAPI backend that serves the Opendle chess opening puzzle game with:
- **Daily puzzle API** — same puzzle for all players each day, with optional manual overrides
- **Global stats collection** — anonymous aggregate game data
- **Dev dashboard** — browser UI to set daily picks, view analytics, browse the opening DB
- **Static file serving** — serves the frontend directly (no separate web server needed)

---

## Project Structure

```
opendle-backend/
├── app/
│   └── main.py          # All API routes + server logic
├── static/
│   ├── index.html       # Game frontend (your opendle HTML + API bridge)
│   └── dashboard.html   # Dev dashboard
├── data/
│   ├── openings.json    # Opening database (extracted from frontend)
│   ├── daily_picks.json # Manual daily overrides (auto-created)
│   └── global_stats.json # Aggregate play stats (auto-created)
├── requirements.txt
├── run.py               # Dev server entry point
├── Dockerfile
└── .env.example
```

---

## Quick Start (Local)

```bash
# 1. Clone / unzip the project
cd opendle-backend

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and edit env config
cp .env.example .env
# Edit .env and set a strong DEV_KEY

# 4. Start the server
python run.py

# 5. Open the game
open http://localhost:8000/

# 6. Open the dashboard
open http://localhost:8000/dashboard
```

---

## Deployment

### Render (recommended — free tier available)

1. Push this folder to a GitHub repo
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your repo
4. **Build command:** `pip install -r requirements.txt`
5. **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Add environment variable: `DEV_KEY = your-secret-key-here`
7. Deploy

> **Persistent storage note:** Render's free tier has an ephemeral filesystem — `data/` will reset on redeploy. For production, use a Render Disk (paid) or replace the JSON storage with SQLite/Postgres.

### Railway

```bash
railway init
railway up
railway variables set DEV_KEY=your-secret-key
```

### Docker

```bash
docker build -t opendle .
docker run -p 8000:8000 \
  -e DEV_KEY=your-secret-key \
  -v $(pwd)/data:/app/data \   # mount data dir for persistence
  opendle
```

### Fly.io

```bash
flyctl launch
flyctl secrets set DEV_KEY=your-secret-key
flyctl deploy
```

---

## API Reference

### Public Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve game frontend |
| GET | `/dashboard` | Serve dev dashboard |
| GET | `/api/daily/{diff}` | Today's daily puzzle (`beginner`/`intermediate`/`master`) |
| GET | `/api/openings` | All openings (optional `?diff=beginner&family=Sicilian`) |
| GET | `/api/openings/{name}` | Single opening by name |
| POST | `/api/stats/submit` | Submit anonymous game result |
| GET | `/api/stats/global` | Public aggregate stats |
| GET | `/health` | Liveness probe |

### Dev Endpoints (require `X-Dev-Key` header)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dev/stats` | Full internal stats for dashboard |
| GET | `/api/dev/picks` | All manual daily pick overrides |
| POST | `/api/dev/picks` | Set a daily pick |
| DELETE | `/api/dev/picks/{date}/{diff}` | Remove a daily pick override |
| GET | `/api/dev/calendar?days=30` | Upcoming puzzle schedule |
| GET | `/api/dev/openings` | Opening list with search (`?search=sicilian&diff=master`) |
| POST | `/api/dev/openings` | Add new opening to database |

### Stats Submit Payload

```json
POST /api/stats/submit
{
  "difficulty": "beginner",
  "mode": "daily",
  "won": true,
  "guesses": 3,
  "opening_name": "Ruy Lopez",
  "date": "2025-01-15"
}
```

---

## Chessboard CDN

The frontend uses inline SVG pieces (self-contained, no CDN dependency).

For **better piece graphics**, swap to [Lichess piece sets via UNPKG](https://unpkg.com/@lichess-org/board@2.0.0/):

```html
<!-- In index.html <head>, add: -->
<link rel="stylesheet" href="https://unpkg.com/@lichess-org/board@2.0.0/dist/board.css">
```

Or use the **chessboard.js CDN** (already referenced in the v5 code):
```html
<link rel="stylesheet"
  href="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.css"
  crossorigin="anonymous">
<script src="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.js"
  crossorigin="anonymous"></script>
```

Recommended piece set CDNs ranked by visual quality:
1. **Lichess pieces** — `https://lichess1.org/assets/piece/cburnett/` (Merida/CBurnett, best quality)
2. **chessboard.js** — `https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/` (easy drop-in)
3. **chess-pieces npm** — `https://unpkg.com/chess-pieces@1.0.5/` (SVG, crisp at any size)

---

## Dev Dashboard Usage

1. Open `/dashboard`
2. Enter your `DEV_KEY` in the sidebar and click **Authenticate**
3. **Analytics** — view total games, win rate, guess distribution, mode breakdown, 14-day trend, top openings
4. **Daily Picks** — override any date's puzzle by picking a date + difficulty + opening name
5. **Calendar** — see the next 30 days of puzzles (gold = manual, grey = auto-generated)
6. **Openings** — browse/search the full opening database

---

## How Daily Puzzles Work

1. If a **manual override** is set for today's date + difficulty in `data/daily_picks.json`, that opening is served
2. Otherwise, a **deterministic hash** of `date + difficulty` selects an opening from the pool — the same opening is returned every time for the same date, without any database

This means:
- All players get the same puzzle with no coordination needed
- You can plan ahead by setting manual picks weeks in advance
- If you set no picks, the game still works perfectly forever
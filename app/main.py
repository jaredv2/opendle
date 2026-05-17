"""
Opendle Backend API
===================
FastAPI server that serves the Opendle frontend and provides:
- Daily puzzle API (deterministic, same puzzle for everyone each day)
- Opening database API
- Stats / analytics endpoints
- Dev dashboard API for managing daily picks and reviewing data
"""

import json
import hashlib
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ──────────────────────────────────────────────────────────────────────────────
# Logging — every action prints a debug trace so you can follow the flow
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("opendle")

# ──────────────────────────────────────────────────────────────────────────────
# App init
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Opendle API", version="1.0.0")

# Allow requests from the frontend (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent
DATA_DIR = BASE / "data"
STATIC_DIR = BASE / "static"
DATA_DIR.mkdir(exist_ok=True)

DAILY_PICKS_FILE = DATA_DIR / "daily_picks.json"
STATS_FILE       = DATA_DIR / "global_stats.json"
OPENINGS_FILE    = DATA_DIR / "openings.json"

# ──────────────────────────────────────────────────────────────────────────────
# Simple admin key guard  (set DEV_KEY env var in production)
# ──────────────────────────────────────────────────────────────────────────────
import os
DEV_KEY = os.getenv("DEV_KEY", "opendle-dev-secret")

def require_dev(x_dev_key: Optional[str] = Header(None)):
    """Dependency that validates the dev dashboard API key."""
    log.debug(f"[auth] Checking dev key: {x_dev_key!r}")
    if x_dev_key != DEV_KEY:
        log.warning("[auth] Unauthorized dev access attempt")
        raise HTTPException(status_code=401, detail="Invalid or missing X-Dev-Key header")
    return True

# ──────────────────────────────────────────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────────────────────────────────────────
def load_json(path: Path, default):
    """Load JSON file, return default if missing."""
    log.debug(f"[data] Loading {path}")
    if not path.exists():
        log.debug(f"[data] {path} not found, returning default")
        return default
    with open(path) as f:
        return json.load(f)

def save_json(path: Path, data):
    """Persist data as pretty JSON."""
    log.debug(f"[data] Saving {path}")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_openings():
    return load_json(OPENINGS_FILE, [])

def load_daily_picks():
    return load_json(DAILY_PICKS_FILE, {})

def load_global_stats():
    return load_json(STATS_FILE, {
        "total_games": 0,
        "total_wins": 0,
        "difficulty_breakdown": {"beginner": 0, "intermediate": 0, "master": 0},
        "mode_breakdown": {"daily": 0, "random": 0, "blitz": 0, "reverse": 0},
        "guess_distribution": [0, 0, 0, 0, 0, 0],
        "popular_openings": {},
        "daily_active": {},   # date -> unique games played
    })

# ──────────────────────────────────────────────────────────────────────────────
# Daily puzzle logic — deterministic fallback if no manual pick is set
# ──────────────────────────────────────────────────────────────────────────────
def get_daily_opening(diff: str, target_date: str) -> Optional[dict]:
    """
    Return today's opening for a given difficulty.
    Priority: manual override in daily_picks.json > deterministic hash pick.
    The deterministic pick ensures everyone gets the same puzzle without a DB.
    """
    log.debug(f"[daily] Resolving opening for diff={diff}, date={target_date}")
    openings = load_openings()

    # Filter by difficulty tier
    tier_map = {"beginner": 1, "intermediate": 2, "master": 3}
    tier = tier_map.get(diff)
    pool = [o for o in openings if o.get("tier") == tier]
    log.debug(f"[daily] Pool size for tier {tier}: {len(pool)}")
    if not pool:
        return None

    # Check for manual override
    picks = load_daily_picks()
    pick_key = f"{target_date}_{diff}"
    if pick_key in picks:
        name = picks[pick_key]
        match = next((o for o in pool if o["name"] == name), None)
        if match:
            log.debug(f"[daily] Using manual pick: {name}")
            return match
        log.warning(f"[daily] Manual pick '{name}' not found in pool, falling back to hash")

    # Deterministic fallback: hash(date + diff) % pool_size
    seed = hashlib.md5(f"{target_date}{diff}".encode()).hexdigest()
    idx = int(seed[:8], 16) % len(pool)
    chosen = pool[idx]
    log.debug(f"[daily] Hash-picked index {idx}: {chosen['name']}")
    return chosen

# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/daily/{diff}")
def daily_puzzle(diff: str, d: Optional[str] = None):
    """
    GET /api/daily/beginner          — today's beginner puzzle
    GET /api/daily/intermediate      — today's intermediate puzzle
    GET /api/daily/master            — today's master puzzle
    Optional ?d=YYYY-MM-DD to fetch a past day (for testing).
    """
    log.info(f"[route] GET /api/daily/{diff} d={d}")
    if diff not in ("beginner", "intermediate", "master"):
        raise HTTPException(400, "diff must be beginner | intermediate | master")
    target = d or str(date.today())
    opening = get_daily_opening(diff, target)
    if not opening:
        raise HTTPException(404, "No openings found for this difficulty")
    return {"date": target, "difficulty": diff, "opening": opening}


@app.get("/api/openings")
def list_openings(diff: Optional[str] = None, family: Optional[str] = None):
    """
    GET /api/openings                — all openings
    GET /api/openings?diff=beginner  — filter by difficulty
    GET /api/openings?family=Sicilian — filter by family
    Used by the frontend autocomplete and game init.
    """
    log.info(f"[route] GET /api/openings diff={diff} family={family}")
    openings = load_openings()
    tier_map = {"beginner": 1, "intermediate": 2, "master": 3}
    if diff and diff in tier_map:
        openings = [o for o in openings if o.get("tier") == tier_map[diff]]
    if family:
        openings = [o for o in openings if o.get("family", "").lower() == family.lower()]
    log.debug(f"[route] Returning {len(openings)} openings")
    return {"count": len(openings), "openings": openings}


@app.get("/api/openings/{name}")
def get_opening(name: str):
    """GET /api/openings/Ruy%20Lopez — fetch a single opening by name."""
    log.info(f"[route] GET /api/openings/{name}")
    openings = load_openings()
    match = next((o for o in openings if o["name"].lower() == name.lower()), None)
    if not match:
        raise HTTPException(404, "Opening not found")
    return match


# ──────────────────────────────────────────────────────────────────────────────
# Stats submission — frontend POSTs after each game
# ──────────────────────────────────────────────────────────────────────────────
class GameResult(BaseModel):
    difficulty: str          # beginner | intermediate | master
    mode: str                # daily | random | blitz | reverse
    won: bool
    guesses: int             # 1-6
    opening_name: str
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today

@app.post("/api/stats/submit")
def submit_stats(result: GameResult):
    """
    POST /api/stats/submit
    Called by the frontend at game end to aggregate anonymous global stats.
    No personal data — purely aggregate counters.
    """
    log.info(f"[route] POST /api/stats/submit: {result.dict()}")
    stats = load_global_stats()
    today = result.date or str(date.today())

    stats["total_games"] += 1
    if result.won:
        stats["total_wins"] += 1
        if 1 <= result.guesses <= 6:
            stats["guess_distribution"][result.guesses - 1] += 1

    if result.difficulty in stats["difficulty_breakdown"]:
        stats["difficulty_breakdown"][result.difficulty] += 1

    if result.mode in stats["mode_breakdown"]:
        stats["mode_breakdown"][result.mode] += 1

    # Track popular openings
    oname = result.opening_name
    if oname not in stats["popular_openings"]:
        stats["popular_openings"][oname] = {"seen": 0, "wins": 0}
    stats["popular_openings"][oname]["seen"] += 1
    if result.won:
        stats["popular_openings"][oname]["wins"] += 1

    # Daily active counter
    if today not in stats["daily_active"]:
        stats["daily_active"][today] = 0
    stats["daily_active"][today] += 1

    save_json(STATS_FILE, stats)
    log.debug(f"[stats] Updated: total_games={stats['total_games']}")
    return {"ok": True}


@app.get("/api/stats/global")
def global_stats():
    """GET /api/stats/global — aggregated anonymous play stats (public)."""
    log.info("[route] GET /api/stats/global")
    stats = load_global_stats()
    win_rate = round(stats["total_wins"] / max(stats["total_games"], 1) * 100, 1)
    return {**stats, "win_rate_pct": win_rate}


# ══════════════════════════════════════════════════════════════════════════════
# DEV DASHBOARD API  (protected by X-Dev-Key header)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/dev/picks", dependencies=[Depends(require_dev)])
def dev_get_picks():
    """GET /api/dev/picks — list all manually set daily picks."""
    log.info("[dev] GET /api/dev/picks")
    picks = load_daily_picks()
    return {"picks": picks}


class DailyPickSet(BaseModel):
    date: str        # YYYY-MM-DD
    difficulty: str  # beginner | intermediate | master
    opening_name: str

@app.post("/api/dev/picks", dependencies=[Depends(require_dev)])
def dev_set_pick(body: DailyPickSet):
    """
    POST /api/dev/picks
    Manually override what opening appears on a given date for a difficulty.
    """
    log.info(f"[dev] POST /api/dev/picks: {body.dict()}")
    openings = load_openings()
    match = next((o for o in openings if o["name"].lower() == body.opening_name.lower()), None)
    if not match:
        raise HTTPException(404, f"Opening '{body.opening_name}' not found in database")
    picks = load_daily_picks()
    key = f"{body.date}_{body.difficulty}"
    picks[key] = match["name"]
    save_json(DAILY_PICKS_FILE, picks)
    log.info(f"[dev] Saved pick: {key} -> {match['name']}")
    return {"ok": True, "key": key, "opening": match["name"]}


@app.delete("/api/dev/picks/{date}/{diff}", dependencies=[Depends(require_dev)])
def dev_delete_pick(date: str, diff: str):
    """DELETE /api/dev/picks/2025-01-15/beginner — remove a manual override."""
    log.info(f"[dev] DELETE pick {date}/{diff}")
    picks = load_daily_picks()
    key = f"{date}_{diff}"
    if key not in picks:
        raise HTTPException(404, "Pick not found")
    del picks[key]
    save_json(DAILY_PICKS_FILE, picks)
    return {"ok": True, "deleted": key}


@app.get("/api/dev/stats", dependencies=[Depends(require_dev)])
def dev_stats_full():
    """GET /api/dev/stats — full internal stats for the dev dashboard."""
    log.info("[dev] GET /api/dev/stats")
    stats = load_global_stats()
    openings = load_openings()

    # Enrich popular openings with opening metadata
    enriched = []
    for name, s in sorted(stats["popular_openings"].items(),
                           key=lambda x: x[1]["seen"], reverse=True)[:20]:
        o = next((op for op in openings if op["name"] == name), {})
        enriched.append({
            "name": name,
            "seen": s["seen"],
            "wins": s["wins"],
            "win_rate": round(s["wins"] / max(s["seen"], 1) * 100, 1),
            "difficulty": {1: "Beginner", 2: "Intermediate", 3: "Master"}.get(o.get("tier"), "?"),
            "eco": o.get("eco", "?"),
        })

    # Last 14 days of activity
    today = date.today()
    daily_trend = []
    for i in range(13, -1, -1):
        d = str(today - timedelta(days=i))
        daily_trend.append({"date": d, "games": stats["daily_active"].get(d, 0)})

    return {
        "summary": {
            "total_games": stats["total_games"],
            "total_wins": stats["total_wins"],
            "win_rate_pct": round(stats["total_wins"] / max(stats["total_games"], 1) * 100, 1),
            "total_openings_in_db": len(openings),
        },
        "difficulty_breakdown": stats["difficulty_breakdown"],
        "mode_breakdown": stats["mode_breakdown"],
        "guess_distribution": stats["guess_distribution"],
        "popular_openings": enriched,
        "daily_trend": daily_trend,
    }


@app.get("/api/dev/openings", dependencies=[Depends(require_dev)])
def dev_list_openings(search: Optional[str] = None, diff: Optional[str] = None):
    """GET /api/dev/openings — list openings with optional search for the picker UI."""
    log.info(f"[dev] GET /api/dev/openings search={search} diff={diff}")
    openings = load_openings()
    tier_map = {"beginner": 1, "intermediate": 2, "master": 3}
    if diff and diff in tier_map:
        openings = [o for o in openings if o.get("tier") == tier_map[diff]]
    if search:
        q = search.lower()
        openings = [o for o in openings if q in o["name"].lower() or q in o.get("family", "").lower()]
    return {"count": len(openings), "openings": [
        {"name": o["name"], "eco": o["eco"], "family": o["family"],
         "tier": o["tier"], "moves_count": len(o.get("moves", []))}
        for o in openings
    ]}


@app.get("/api/dev/calendar", dependencies=[Depends(require_dev)])
def dev_calendar(days: int = 30):
    """
    GET /api/dev/calendar?days=30
    Returns the next N days of puzzles for all difficulties, 
    showing which are manual picks vs auto-generated.
    """
    log.info(f"[dev] GET /api/dev/calendar days={days}")
    picks = load_daily_picks()
    today = date.today()
    calendar = []
    for i in range(days):
        d = str(today + timedelta(days=i))
        day_entry = {"date": d, "puzzles": {}}
        for diff in ("beginner", "intermediate", "master"):
            key = f"{d}_{diff}"
            opening = get_daily_opening(diff, d)
            day_entry["puzzles"][diff] = {
                "opening": opening["name"] if opening else None,
                "eco": opening.get("eco") if opening else None,
                "is_manual": key in picks,
            }
        calendar.append(day_entry)
    return {"calendar": calendar}


@app.post("/api/dev/openings", dependencies=[Depends(require_dev)])
def dev_add_opening(opening: dict):
    """POST /api/dev/openings — add a new opening to the database."""
    log.info(f"[dev] POST /api/dev/openings: {opening.get('name')}")
    openings = load_openings()
    required = {"name", "eco", "family", "tier", "moves", "pawn", "move1", "desc"}
    missing = required - set(opening.keys())
    if missing:
        raise HTTPException(400, f"Missing fields: {missing}")
    if any(o["name"].lower() == opening["name"].lower() for o in openings):
        raise HTTPException(409, "Opening with this name already exists")
    openings.append(opening)
    save_json(OPENINGS_FILE, openings)
    log.info(f"[dev] Added opening: {opening['name']}")
    return {"ok": True, "total": len(openings)}


# ──────────────────────────────────────────────────────────────────────────────
# Static file serving — serve the frontend
# ──────────────────────────────────────────────────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=FileResponse)
def serve_game():
    """Serve the main Opendle game HTML."""
    log.info("[route] GET / - serving game")
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Frontend not found. Place index.html in /static/</h1>", 404)
    return FileResponse(str(index))

@app.get("/dashboard", response_class=FileResponse)
def serve_dashboard():
    """Serve the dev dashboard HTML."""
    log.info("[route] GET /dashboard")
    dash = STATIC_DIR / "dashboard.html"
    if not dash.exists():
        return HTMLResponse("<h1>Dashboard not found. Place dashboard.html in /static/</h1>", 404)
    return FileResponse(str(dash))

@app.get("/health")
def health():
    """Simple liveness probe for deployment platforms."""
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
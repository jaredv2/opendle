"""
Opendle server entry point.
Run with:  python run.py
Or for development with auto-reload:  uvicorn app.main:app --reload --port 8000
"""
import os
import logging
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Load .env file if present (ignored in production where env vars are set externally)
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"[run] Loaded .env from {env_file}")
else:
    print("[run] No .env file found — using environment variables or defaults")

# Debug print all relevant env vars (mask the key)
dev_key = os.getenv("DEV_KEY", "opendle-dev-secret")
host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "8000"))

print(f"[run] DEV_KEY set: {'yes (custom)' if dev_key != 'opendle-dev-secret' else 'NO — using default, change before production!'}")
print(f"[run] Binding to {host}:{port}")
print(f"[run] Game:      http://localhost:{port}/")
print(f"[run] Dashboard: http://localhost:{port}/dashboard")
print(f"[run] API docs:  http://localhost:{port}/docs")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,          # Set to False in production
        log_level="debug",
        access_log=True,
    )
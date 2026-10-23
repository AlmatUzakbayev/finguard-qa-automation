"""FinGuard - a training banking API built as a target for QA automation.

NOT a real banking system: no real money, no certification, no production hardening.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.errors import register_error_handlers
from app.routers import accounts, auth, transfers

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="FinGuard API",
    version="1.0.0",
    description="Training banking API for QA automation practice. Not for real money.",
)
register_error_handlers(app)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transfers.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# The minimal web UI is plain static HTML/JS that calls the API above.
# Mounted last so that it never shadows /api routes.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

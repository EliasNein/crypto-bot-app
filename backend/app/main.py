"""FastAPI-App für das read-only Trading-Bot-Dashboard.

Komplett eigenständig vom crypto-bot-Projekt: es wird nichts von dort
importiert, kein Binance-Client existiert in diesem Code, und die vier
Ledger-Dateien werden ausschließlich mit json.load() gelesen (siehe
ledger_readers.py). Schreibender Zugriff kommt in diesem Projekt nirgendwo
vor.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import verify_token
from .ledger_readers import (
    summarize_allocator,
    summarize_dca,
    summarize_grid,
    summarize_overview,
    summarize_trend,
)

load_dotenv()

app = FastAPI(title="Trading Bot Dashboard API")

_cors_origins = os.getenv("CORS_ORIGINS", "*")
_origins = ["*"] if _cors_origins.strip() == "*" else [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _data_dir() -> Path:
    """Der EINE Ordner, aus dem alle vier Ledger-Dateien gelesen werden.

    Bewusst keine zweite/weitere Datenquelle: Homeserver und VPS führen
    laut Projektdokumentation getrennte Testreihen, und dieses Dashboard
    soll ausschließlich die Homeserver-Daten zeigen. Es gibt hier absichtlich
    keine Mehrserver- oder Pfad-Auswahl-Logik - beim Deploy zeigt DATA_DIR
    auf den data/-Ordner des Homeservers, sonst nirgendwohin.
    """
    configured = os.getenv("DATA_DIR")
    if configured:
        return Path(configured)
    # Default für die lokale Entwicklung: data/ im Projekt-Root.
    return Path(__file__).resolve().parents[2] / "data"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status", dependencies=[Depends(verify_token)])
def status() -> dict:
    data_dir = _data_dir()
    dca_path = data_dir / "trade_ledger.json"
    grid_path = data_dir / "grid_positions.json"
    trend_path = data_dir / "trend_ledger.json"
    return {
        "dca": summarize_dca(dca_path),
        "grid": summarize_grid(grid_path),
        "trend": summarize_trend(trend_path),
        "allocator": summarize_allocator(data_dir / "allocator_state.json"),
        "overview": summarize_overview(dca_path, grid_path, trend_path),
    }

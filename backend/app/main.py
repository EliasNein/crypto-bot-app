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
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import verify_token
from .export import build_trades_csv
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


def _ledger_paths() -> tuple[Path, Path, Path]:
    data_dir = _data_dir()
    return (
        data_dir / "trade_ledger.json",
        data_dir / "grid_positions.json",
        data_dir / "trend_ledger.json",
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status", dependencies=[Depends(verify_token)])
def status() -> dict:
    dca_path, grid_path, trend_path = _ledger_paths()
    return {
        "dca": summarize_dca(dca_path),
        "grid": summarize_grid(grid_path),
        "trend": summarize_trend(trend_path),
        "allocator": summarize_allocator(_data_dir() / "allocator_state.json"),
        "overview": summarize_overview(dca_path, grid_path, trend_path),
    }


@app.get("/api/export/trades", dependencies=[Depends(verify_token)])
def export_trades(period: str = Query(default="all")) -> Response:
    """CSV-Export aller echten Trades - siehe export.py für die Regeln
    (nur dry_run=false, Kauf/Verkauf-Zeilen, Kommentarblock am Ende,
    optionale Zeitraum-Filterung über ?period=week|month|year|all).
    """
    dca_path, grid_path, trend_path = _ledger_paths()
    try:
        csv_content = build_trades_csv(dca_path, grid_path, trend_path, period=period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades_export.csv"},
    )


# Das Frontend wird von derselben Instanz ausgeliefert wie die API - auf dem
# Homeserver läuft damit genau ein Prozess auf einem Port, kein zweiter
# Webserver für die statischen Dateien.
#
# Dieser Mount MUSS nach allen API-Routen stehen: Starlette prüft die Routen
# in Registrierungsreihenfolge, ein Mount auf "/" würde sonst /health und
# /api/... verschlucken.
#
# html=True liefert index.html automatisch als Startseite aus.
_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")

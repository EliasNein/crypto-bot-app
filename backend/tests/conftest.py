"""Gemeinsame Fixtures für die Browser-Tests.

Genutzt von test_frontend_login_flow.py und test_frontend_dashboard.py.
Playwright wird erst INNERHALB der Fixtures importiert: Fehlt es,
überspringen sich nur die Tests, die einen Browser anfordern - der Rest
der Suite läuft normal durch.

Braucht `playwright` (siehe requirements-dev.txt) plus einmalig
`python -m playwright install chromium`.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
TOKEN = "e4b1" * 16  # 64 Zeichen, besteht den Entropie-Check in auth.py


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def server() -> str:
    """Echter uvicorn-Prozess - der Browser braucht eine erreichbare
    Adresse, ein TestClient genügt hier nicht. Liefert die Basis-URL."""
    port = _free_port()
    env = {**os.environ, "DASHBOARD_TOKEN": TOKEN}
    env.pop("DATA_DIR", None)  # Default: data/ im Projekt-Root (Beispieldaten)

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if process.poll() is not None:
                raise RuntimeError("uvicorn ist beim Start abgebrochen")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("uvicorn wurde nicht rechtzeitig erreichbar")

        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright nicht installiert (siehe requirements-dev.txt)"
    ).sync_playwright
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def page(browser):
    # Frischer Kontext pro Test => leerer LocalStorage, wie bei einem
    # Besucher, der die Seite zum ersten Mal öffnet.
    context = browser.new_context(viewport={"width": 420, "height": 900})
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()

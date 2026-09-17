"""Token-Check für die geschützten API-Endpunkte.

Liest DASHBOARD_TOKEN bei jedem Request neu aus der Umgebung (statt es
beim Modul-Import einzufrieren) - das macht die Dependency in Tests mit
monkeypatch.setenv() beeinflussbar und auf dem Server per Restart
austauschbar, ohne Code-Änderung.

Das Token wird AUSSCHLIESSLICH über den Header X-Dashboard-Token
akzeptiert. Der frühere ?token=-Query-Parameter ist bewusst entfernt:
Query-Strings landen im uvicorn-Access-Log, in der Browser-History und
- sobald die App über den Cloudflare Tunnel läuft - zusätzlich in
Cloudflares Request-Logs. Ein Header tut das nicht.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger(__name__)

# Ein Token aus `openssl rand -hex 32` hat 64 Zeichen. Alles unter 32
# Zeichen ist für einen öffentlich erreichbaren Endpunkt zu schwach -
# und weil es hier bewusst KEINE Rate-Limitierung gibt, ist die Entropie
# des Tokens die einzige Schutzschicht. Deshalb wird sie erzwungen statt
# nur im README empfohlen.
MIN_TOKEN_LENGTH = 32

# Werte aus .env.example bzw. typische Platzhalter, die nie produktiv
# gelten dürfen - auch dann nicht, wenn sie lang genug wären.
PLACEHOLDER_TOKENS = frozenset({"change-me", "changeme", "secret", "token", "test"})


def _configured_token() -> str:
    """Das Server-Token, oder HTTPException(500) wenn es unbrauchbar ist.

    Fail closed: lieber gar keine Auslieferung als eine mit einem Token,
    das in Sekunden zu erraten wäre.
    """
    expected = os.getenv("DASHBOARD_TOKEN", "")

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DASHBOARD_TOKEN ist auf dem Server nicht gesetzt.",
        )

    if expected.strip().lower() in PLACEHOLDER_TOKENS or len(expected) < MIN_TOKEN_LENGTH:
        logger.error(
            "DASHBOARD_TOKEN ist zu schwach (mindestens %d Zeichen, kein Platzhalter). "
            "Neues Token erzeugen mit: openssl rand -hex 32",
            MIN_TOKEN_LENGTH,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DASHBOARD_TOKEN ist auf dem Server unsicher konfiguriert.",
        )

    return expected


def _client_identifier(request: Request) -> str:
    """Woher der Request kam - hinter dem Cloudflare Tunnel steht in
    request.client nur die lokale Tunnel-Adresse, die echte Client-IP
    liefert Cloudflare in CF-Connecting-IP.
    """
    forwarded = request.headers.get("CF-Connecting-IP")
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unbekannt"


def verify_token(
    request: Request,
    x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
) -> None:
    expected = _configured_token()

    # compare_digest statt "!=", damit die Vergleichsdauer nicht vom
    # gemeinsamen Präfix abhängt. Über das Internet ist dieses Signal
    # praktisch im Rauschen, der Fix kostet aber nichts.
    provided = x_dashboard_token or ""
    if not secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        # Ohne diese Zeile wäre ein Rateversuch unsichtbar - es gibt sonst
        # kein Log für 401er. Das übermittelte Token wird bewusst NICHT
        # mitgeloggt.
        logger.warning(
            "Abgelehnter Zugriff auf %s von %s (Token %s).",
            request.url.path,
            _client_identifier(request),
            "falsch" if provided else "fehlt",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder fehlendes Token.",
        )

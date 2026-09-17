"""Token-Check für /api/status.

Liest DASHBOARD_TOKEN bei jedem Request neu aus der Umgebung (statt es
beim Modul-Import einzufrieren) - das macht die Dependency in Tests mit
monkeypatch.setenv() beeinflussbar und auf dem Server per Restart
austauschbar, ohne Code-Änderung.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, Query, status


def verify_token(
    x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
    token: str | None = Query(default=None),
) -> None:
    expected = os.getenv("DASHBOARD_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DASHBOARD_TOKEN ist auf dem Server nicht gesetzt.",
        )

    provided = x_dashboard_token or token
    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder fehlendes Token.",
        )

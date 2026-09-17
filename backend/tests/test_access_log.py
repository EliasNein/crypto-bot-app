"""Der Access-Log-Filter darf Geheimnisse nie durchlassen, harmlose
Parameter aber unangetastet lassen."""

import logging

import pytest

from app.access_log import REDACTED, RedactSensitiveQueryParams, install, redact_query_string


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Genau der Fall aus dem Sicherheitsreview: alter Bookmark mit Token.
        ("/api/export/trades?token=geheim123", f"/api/export/trades?token={REDACTED}"),
        ("/api/status?token=geheim123", f"/api/status?token={REDACTED}"),
        # Gross-/Kleinschreibung darf nicht daran vorbeikommen.
        ("/api/status?TOKEN=geheim123", f"/api/status?TOKEN={REDACTED}"),
        # Harmlose Parameter bleiben lesbar - die braucht man zur Fehlersuche.
        ("/api/export/trades?period=year", "/api/export/trades?period=year"),
        # Mischung: nur der sensible Teil verschwindet.
        (
            "/api/export/trades?period=year&token=geheim123",
            f"/api/export/trades?period=year&token={REDACTED}",
        ),
        # Weitere ueblichen Geheimnis-Namen.
        ("/x?api_key=abc", f"/x?api_key={REDACTED}"),
        ("/x?secret=abc", f"/x?secret={REDACTED}"),
        # Ohne Query-String unveraendert.
        ("/api/status", "/api/status"),
        ("/api/status?", "/api/status?"),
    ],
)
def test_redact_query_string(raw, expected):
    assert redact_query_string(raw) == expected


def test_token_value_never_survives_redaction():
    result = redact_query_string("/api/status?token=streng-geheim")
    assert "streng-geheim" not in result


def test_filter_rewrites_uvicorn_log_record():
    """uvicorn loggt mit '%s - \"%s %s HTTP/%s\" %d'; der Pfad steht an
    Position 2 der Argumente."""
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", "/api/status?token=geheim123", "1.1", 401),
        exc_info=None,
    )

    assert RedactSensitiveQueryParams().filter(record) is True
    assert "geheim123" not in record.getMessage()
    assert REDACTED in record.getMessage()


def test_filter_leaves_unrelated_records_alone():
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Einfache Nachricht ohne Argumente",
        args=None,
        exc_info=None,
    )

    assert RedactSensitiveQueryParams().filter(record) is True
    assert record.getMessage() == "Einfache Nachricht ohne Argumente"


def test_install_is_idempotent():
    logger = logging.getLogger("uvicorn.access")
    before = [f for f in logger.filters if isinstance(f, RedactSensitiveQueryParams)]
    install()
    install()
    after = [f for f in logger.filters if isinstance(f, RedactSensitiveQueryParams)]
    assert len(after) == 1
    assert len(before) <= 1

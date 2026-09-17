"""Hält Geheimnisse aus den uvicorn-Access-Logs heraus.

Die App akzeptiert das Token nur noch im Header und erzeugt selbst keine
URL mehr, die eins enthält. uvicorn loggt die angefragte URL aber
unabhängig davon - auch dann, wenn der Request mit 401 abgelehnt wird.
Ein alter Bookmark oder History-Eintrag aus der Zeit des
?token=-Parameters würde das Token damit weiterhin im Klartext ins Log
schreiben. Dieser Filter schließt den letzten verbliebenen Weg.

Andere Parameter (z.B. period=year) bleiben unverändert sichtbar - sie
sind für die Fehlersuche nützlich und harmlos.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode

SENSITIVE_PARAMS = frozenset(
    {"token", "access_token", "auth", "api_key", "key", "secret", "password"}
)

# Bewusst nur ASCII-Buchstaben: urlencode() lässt den Marker damit
# unverändert stehen. Das Escaping der übrigen Werte bleibt aktiv - es
# verhindert, dass Sonderzeichen (etwa Zeilenumbrüche) aus einem
# Query-String die Log-Zeile manipulieren.
REDACTED = "REDACTED"

# Position des Pfads in den Log-Argumenten von uvicorn:
#   '%s - "%s %s HTTP/%s" %d' % (client, method, pfad_mit_query, version, status)
_PATH_ARG_INDEX = 2


def redact_query_string(path_with_query: str) -> str:
    path, separator, query = path_with_query.partition("?")
    if not separator or not query:
        return path_with_query

    pairs = parse_qsl(query, keep_blank_values=True)
    if not pairs:
        # Query-String vorhanden, aber nicht auswertbar: im Zweifel ganz
        # weglassen, statt ungeprüft durchzureichen.
        return path

    return "{}?{}".format(
        path,
        urlencode([(key, REDACTED if key.lower() in SENSITIVE_PARAMS else value) for key, value in pairs]),
    )


class RedactSensitiveQueryParams(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) > _PATH_ARG_INDEX:
            path = args[_PATH_ARG_INDEX]
            if isinstance(path, str) and "?" in path:
                record.args = args[:_PATH_ARG_INDEX] + (redact_query_string(path),) + args[_PATH_ARG_INDEX + 1 :]
        return True


def install() -> None:
    """Hängt den Filter an den uvicorn-Access-Logger.

    Wird beim Import von app.main aufgerufen - also nachdem uvicorn seine
    eigene Logging-Konfiguration angewendet hat, weil die Config vor dem
    Laden der App aufgebaut wird. Der Filter überlebt dictConfig deshalb.
    """
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(existing, RedactSensitiveQueryParams) for existing in logger.filters):
        logger.addFilter(RedactSensitiveQueryParams())

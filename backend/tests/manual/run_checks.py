"""Startet alles, was die manuellen Browser-Prüfungen brauchen, und führt sie aus.

NOCH NICHT TEIL DER PYTEST-SUITE - siehe README.md in diesem Ordner.

Aufruf (aus backend/):  python tests/manual/run_checks.py

1. erzeugt die drei synthetischen Datensätze (fixtures.py) in einem Temp-Ordner
2. startet je Datensatz einen uvicorn-Prozess auf einem freien Port
3. führt verify_round2.py und measure_round2.py aus
4. beendet die Server wieder - auch wenn eine Prüfung abbricht

Exit-Code 1, wenn eines der beiden Skripte fehlschlägt.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
BACKEND = HIER.parents[1]
TOKEN = "demo-token-zum-lokalen-anschauen-2026"

sys.path.insert(0, str(HIER))
from fixtures import schreibe_alle  # noqa: E402


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def starte_server(data_dir: Path) -> tuple[subprocess.Popen, int]:
    port = freier_port()
    env = {**os.environ, "DASHBOARD_TOKEN": TOKEN, "DATA_DIR": str(data_dir)}
    prozess = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    frist = time.time() + 30
    while time.time() < frist:
        if prozess.poll() is not None:
            raise RuntimeError(f"uvicorn für {data_dir.name} ist beim Start abgebrochen")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return prozess, port
        except OSError:
            time.sleep(0.2)
    prozess.terminate()
    raise RuntimeError(f"uvicorn für {data_dir.name} wurde nicht rechtzeitig erreichbar")


def main() -> int:
    prozesse = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ordner = schreibe_alle(Path(tmp))
            ports = {}
            for name in ("demo", "nur_dry_run", "ein_abschluss"):
                prozess, port = starte_server(ordner[name])
                prozesse.append(prozess)
                ports[name] = port

            print("=" * 70, flush=True)
            print("verify_round2.py - Ergebnis-Block und Aufklappen", flush=True)
            print("=" * 70, flush=True)
            rc_verify = subprocess.call([
                sys.executable, str(HIER / "verify_round2.py"),
                str(ports["demo"]), str(ports["nur_dry_run"]), str(ports["ein_abschluss"]),
            ])

            print(flush=True)
            print("=" * 70, flush=True)
            print("measure_round2.py - Struktur + kein Informationsverlust", flush=True)
            print("=" * 70, flush=True)
            rc_measure = subprocess.call([
                sys.executable, str(HIER / "measure_round2.py"), "aktuell", str(ports["demo"]),
            ])
    finally:
        for prozess in prozesse:
            prozess.terminate()
            prozess.wait(timeout=10)

    print()
    gesamt = "BESTANDEN" if rc_verify == 0 and rc_measure == 0 else "FEHLGESCHLAGEN"
    print(f"Gesamt: {gesamt}  (verify={rc_verify}, measure={rc_measure})")
    print(f"Screenshots: {HIER / 'out'}")
    return 0 if gesamt == "BESTANDEN" else 1


if __name__ == "__main__":
    sys.exit(main())

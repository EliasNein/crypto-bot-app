"""Heartbeat-Status der vier Bot-Prozesse.

Die Einstufung nutzt bewusst nur zwei bot-unabhängige Signale
(gemeldete Fehlschläge, Erfolgsmeldung älter als 48h) - die tatsächlichen
Zyklus-Intervalle kennt diese App nicht zuverlässig.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.ledger_readers import STALE_SUCCESS_SECONDS, summarize_heartbeats

NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
ALLE_BOTS = ("dca", "grid", "trend", "allocator")


def _iso(**delta):
    return (NOW - timedelta(**delta)).isoformat()


def _write_heartbeat(tmp_path, bot, inhalt):
    (tmp_path / f"heartbeat_{bot}.json").write_text(json.dumps(inhalt), encoding="utf-8")


def _gesund(minuten=5):
    return {
        "last_successful_cycle": _iso(minutes=minuten),
        "last_cycle_attempt": _iso(minutes=minuten),
        "consecutive_failures": 0,
    }


def _alle_gesund(tmp_path):
    for bot in ALLE_BOTS:
        _write_heartbeat(tmp_path, bot, _gesund())


# --- Normalfall ------------------------------------------------------------


def test_all_four_files_healthy(tmp_path):
    _alle_gesund(tmp_path)

    result = summarize_heartbeats(tmp_path, now=NOW)

    assert set(result) == set(ALLE_BOTS)
    for bot in ALLE_BOTS:
        assert result[bot]["status"] == "ok", bot
        assert result[bot]["reason"] is None, bot
        assert result[bot]["seconds_since_success"] == pytest.approx(300.0)
        assert result[bot]["seconds_since_attempt"] == pytest.approx(300.0)


def test_raw_file_content_is_passed_through(tmp_path):
    _alle_gesund(tmp_path)
    _write_heartbeat(
        tmp_path,
        "grid",
        {
            "last_successful_cycle": "2026-09-25T11:55:00+00:00",
            "last_cycle_attempt": "2026-09-25T11:57:00+00:00",
            "consecutive_failures": 0,
        },
    )

    grid = summarize_heartbeats(tmp_path, now=NOW)["grid"]

    assert grid["last_successful_cycle"] == "2026-09-25T11:55:00+00:00"
    assert grid["last_cycle_attempt"] == "2026-09-25T11:57:00+00:00"
    assert grid["consecutive_failures"] == 0


# --- Fehlende / kaputte Dateien -------------------------------------------


def test_missing_file_is_no_data_and_does_not_affect_the_others(tmp_path):
    """Ein älteres crypto-bot-Deployment ohne dieses Feature darf keine
    Warnung auslösen - und die anderen drei müssen weiter funktionieren."""
    for bot in ("dca", "grid", "allocator"):
        _write_heartbeat(tmp_path, bot, _gesund())
    # heartbeat_trend.json fehlt komplett

    result = summarize_heartbeats(tmp_path, now=NOW)

    assert result["trend"]["status"] == "no_data"
    assert result["trend"]["reason"] is None  # ausdrücklich keine Warnung
    assert "error" in result["trend"]
    for bot in ("dca", "grid", "allocator"):
        assert result[bot]["status"] == "ok", bot


def test_all_files_missing_yields_four_times_no_data(tmp_path):
    result = summarize_heartbeats(tmp_path, now=NOW)

    assert [result[bot]["status"] for bot in ALLE_BOTS] == ["no_data"] * 4


def test_broken_json_in_one_file_is_isolated(tmp_path):
    _alle_gesund(tmp_path)
    (tmp_path / "heartbeat_grid.json").write_text("{kein gueltiges json", encoding="utf-8")

    result = summarize_heartbeats(tmp_path, now=NOW)

    assert result["grid"]["status"] == "no_data"
    assert result["grid"]["seconds_since_success"] is None
    for bot in ("dca", "trend", "allocator"):
        assert result[bot]["status"] == "ok", bot


def test_json_that_is_not_an_object_is_no_data(tmp_path):
    _alle_gesund(tmp_path)
    (tmp_path / "heartbeat_dca.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    assert summarize_heartbeats(tmp_path, now=NOW)["dca"]["status"] == "no_data"


def test_empty_object_is_no_data(tmp_path):
    _alle_gesund(tmp_path)
    _write_heartbeat(tmp_path, "dca", {})

    assert summarize_heartbeats(tmp_path, now=NOW)["dca"]["status"] == "no_data"


# --- Signal 1: gemeldete Fehlschläge --------------------------------------


def test_consecutive_failures_trigger_a_warning(tmp_path):
    _alle_gesund(tmp_path)
    _write_heartbeat(tmp_path, "grid", {**_gesund(), "consecutive_failures": 4})

    grid = summarize_heartbeats(tmp_path, now=NOW)["grid"]

    assert grid["status"] == "warn"
    assert grid["reason"] == "consecutive_failures"
    assert grid["consecutive_failures"] == 4


def test_failures_win_over_stale_success_because_they_are_more_specific(tmp_path):
    _alle_gesund(tmp_path)
    _write_heartbeat(
        tmp_path,
        "trend",
        {
            "last_successful_cycle": _iso(hours=72),
            "last_cycle_attempt": _iso(minutes=1),
            "consecutive_failures": 9,
        },
    )

    trend = summarize_heartbeats(tmp_path, now=NOW)["trend"]

    assert trend["status"] == "warn"
    assert trend["reason"] == "consecutive_failures"


def test_unreadable_failure_count_does_not_trigger_a_warning(tmp_path):
    """Ein unsinniger Wert wird nicht als Fehlschlag gedeutet - er bleibt
    aber im Response sichtbar, statt still zu 0 zu werden."""
    _alle_gesund(tmp_path)
    _write_heartbeat(tmp_path, "dca", {**_gesund(), "consecutive_failures": "viele"})

    dca = summarize_heartbeats(tmp_path, now=NOW)["dca"]

    assert dca["status"] == "ok"
    assert dca["consecutive_failures"] == "viele"


# --- Signal 2: Erfolgsmeldung zu alt --------------------------------------


def test_success_older_than_48h_is_a_warning(tmp_path):
    _alle_gesund(tmp_path)
    _write_heartbeat(
        tmp_path,
        "dca",
        {"last_successful_cycle": _iso(hours=49), "last_cycle_attempt": _iso(minutes=2), "consecutive_failures": 0},
    )

    dca = summarize_heartbeats(tmp_path, now=NOW)["dca"]

    assert dca["status"] == "warn"
    assert dca["reason"] == "stale_success"
    assert dca["seconds_since_success"] == pytest.approx(49 * 3600)


def test_success_just_under_48h_is_still_ok(tmp_path):
    """Die Grenze darf nicht zu früh greifen - sonst warnt ein
    24h-Takt-Bot nach einem einzigen verspäteten Zyklus."""
    _alle_gesund(tmp_path)
    _write_heartbeat(
        tmp_path,
        "dca",
        {"last_successful_cycle": _iso(hours=47, minutes=59), "last_cycle_attempt": _iso(minutes=2), "consecutive_failures": 0},
    )

    assert summarize_heartbeats(tmp_path, now=NOW)["dca"]["status"] == "ok"


def test_threshold_is_exactly_48_hours(tmp_path):
    assert STALE_SUCCESS_SECONDS == 48 * 3600


def test_future_timestamp_does_not_trigger_a_warning(tmp_path):
    """Uhrenversatz darf keinen Fehlalarm erzeugen."""
    _alle_gesund(tmp_path)
    _write_heartbeat(
        tmp_path,
        "grid",
        {
            "last_successful_cycle": (NOW + timedelta(hours=2)).isoformat(),
            "last_cycle_attempt": (NOW + timedelta(hours=2)).isoformat(),
            "consecutive_failures": 0,
        },
    )

    grid = summarize_heartbeats(tmp_path, now=NOW)["grid"]

    assert grid["status"] == "ok"
    assert grid["seconds_since_success"] < 0


# --- Noch kein erfolgreicher Zyklus ---------------------------------------


def test_null_success_without_failures_is_neutral_not_a_warning(tmp_path):
    """Frisch gestarteter Bot: bei 24h-Takt kann dieser Zustand einen
    ganzen Tag dauern und ist völlig normal."""
    _alle_gesund(tmp_path)
    _write_heartbeat(
        tmp_path,
        "trend",
        {"last_successful_cycle": None, "last_cycle_attempt": _iso(minutes=3), "consecutive_failures": 0},
    )

    trend = summarize_heartbeats(tmp_path, now=NOW)["trend"]

    assert trend["status"] == "ok"
    assert trend["reason"] == "no_confirmed_success"
    assert trend["seconds_since_success"] is None
    assert trend["seconds_since_attempt"] == pytest.approx(180.0)


def test_null_success_with_failures_becomes_a_warning(tmp_path):
    _alle_gesund(tmp_path)
    _write_heartbeat(
        tmp_path,
        "trend",
        {"last_successful_cycle": None, "last_cycle_attempt": _iso(minutes=3), "consecutive_failures": 2},
    )

    trend = summarize_heartbeats(tmp_path, now=NOW)["trend"]

    assert trend["status"] == "warn"
    assert trend["reason"] == "consecutive_failures"


def test_missing_success_field_behaves_like_null(tmp_path):
    _alle_gesund(tmp_path)
    _write_heartbeat(tmp_path, "allocator", {"last_cycle_attempt": _iso(minutes=1), "consecutive_failures": 0})

    allocator = summarize_heartbeats(tmp_path, now=NOW)["allocator"]

    assert allocator["status"] == "ok"
    assert allocator["reason"] == "no_confirmed_success"


def test_unparseable_success_timestamp_is_not_claimed_as_stale(tmp_path):
    """Ein unlesbarer Zeitstempel ist keine bestätigte Erfolgsmeldung -
    aber auch keine Grundlage für eine Altersangabe."""
    _alle_gesund(tmp_path)
    _write_heartbeat(
        tmp_path,
        "dca",
        {"last_successful_cycle": 1758801600, "last_cycle_attempt": _iso(minutes=1), "consecutive_failures": 0},
    )

    dca = summarize_heartbeats(tmp_path, now=NOW)["dca"]

    assert dca["status"] == "ok"
    assert dca["reason"] == "no_confirmed_success"
    assert dca["seconds_since_success"] is None

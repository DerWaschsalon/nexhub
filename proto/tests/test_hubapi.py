"""API-Stand und Anfrage-Kennung zwischen Daemon, Hub und Bot."""
import logging

from nexproto.hubapi import (
    HUB_API_WITHOUT_HEADER,
    REQUEST_ID_LEN,
    RequestIdFilter,
    accept_request_id,
    client_api,
    new_request_id,
    request_id,
)


def test_api_stand_aus_der_kopfzeile():
    assert client_api("3") == 3
    assert client_api(None) == HUB_API_WITHOUT_HEADER  # Daemon von vor der Absprache
    assert client_api("kaputt") == 0  # zählt wie zu alt


def test_kennung_wird_nur_uebernommen_wenn_harmlos():
    assert accept_request_id("abc-123") == "abc-123"
    for bad in (None, "", "a b", "zeile\nneu", "x" * 65):
        got = accept_request_id(bad)
        assert got != bad and len(got) == REQUEST_ID_LEN
    assert new_request_id() != new_request_id()


def test_filter_schreibt_die_kennung_in_die_logzeile():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "x", None, None)
    RequestIdFilter().filter(record)
    assert record.request_id == "-"  # außerhalb einer Anfrage
    token = request_id.set("abc")
    try:
        RequestIdFilter().filter(record)
        assert record.request_id == "abc"
    finally:
        request_id.reset(token)

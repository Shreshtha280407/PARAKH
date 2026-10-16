"""Regression tests for tools/perf_report.py's error-handling contract
(see that module's docstring): a completely unreachable backend, or a
backend whose pack was never imported, must never crash this script with
an uncaught traceback -- every failure mode must come back as a normal,
inspectable part of the JSON report.

No real network/Docker is used here: urllib.request.urlopen is mocked to
simulate specific server behaviors (success, HTTP error, connection
refused) deterministically and fast.
"""
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import perf_report  # noqa: E402


class FakeResponse:
    def __init__(self, status: int, body: dict | None):
        self.status = status
        self._body = json.dumps(body).encode() if body is not None else b""

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _fake_urlopen_factory(handler):
    """handler(method, url) -> FakeResponse, or raises urllib.error.HTTPError/URLError."""

    def fake_urlopen(req, timeout=30):
        return handler(req.get_method(), req.full_url)

    return fake_urlopen


def test_full_success_path_produces_correct_summary_stats():
    def handler(method, url):
        if url.endswith("/auth/login"):
            return FakeResponse(200, {"access_token": "tok"})
        if url.endswith("/queue"):
            return FakeResponse(200, [])
        if "packs/by-code" in url:
            return FakeResponse(200, {"pack_id": 1})
        if url.endswith("/workers/register"):
            return FakeResponse(200, {"worker_id": 1})
        if url.endswith("/assessments"):
            return FakeResponse(201, {"id": 42})
        if url.endswith("/rubric"):
            return FakeResponse(200, [])
        raise AssertionError(f"unexpected call: {method} {url}")

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        report = perf_report.run("http://fake", "a@b.c", "pw", repeat=3)

    by_name = {r["scenario"]: r for r in report["results"]}
    assert set(by_name) == {
        "auth_login", "queue_retrieval", "assessment_bootstrap_register_plus_create", "rubric_retrieval",
    }
    for name, r in by_name.items():
        assert r["status"] == "ok", f"{name}: {r}"
        assert r["observations"] == 3
        assert r["failures"] == 0
        assert r["median_ms"] is not None
        assert r["sample_errors"] == []


def test_pack_lookup_failure_skips_dependent_stages_but_keeps_earlier_results():
    """The real bug this guards against: a 404 from /packs/by-code used to
    raise RuntimeError straight out of run(), discarding the already-
    collected login/queue results and crashing the whole script."""

    def handler(method, url):
        if url.endswith("/auth/login"):
            return FakeResponse(200, {"access_token": "tok"})
        if url.endswith("/queue"):
            return FakeResponse(200, [])
        if "packs/by-code" in url:
            return FakeResponse(404, {"detail": "no imported pack"})
        raise AssertionError(f"unexpected call after pack lookup should have stopped bootstrap: {method} {url}")

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        report = perf_report.run("http://fake", "a@b.c", "pw", repeat=2)

    by_name = {r["scenario"]: r for r in report["results"]}
    assert by_name["auth_login"]["status"] == "ok"
    assert by_name["auth_login"]["observations"] == 2
    assert by_name["queue_retrieval"]["status"] == "ok"
    assert by_name["assessment_bootstrap_register_plus_create"]["status"] == "skipped"
    assert "no imported pack" in by_name["assessment_bootstrap_register_plus_create"]["skip_reason"]
    assert by_name["rubric_retrieval"]["status"] == "skipped"


def test_connection_refused_is_reported_not_raised():
    """The real bug this guards against: a bare urllib.error.URLError
    (connection refused / DNS failure / timeout) was not caught anywhere
    in Client.call(), so an unreachable server crashed the whole script
    with a raw traceback instead of producing a report."""

    def handler(method, url):
        raise urllib.error.URLError("Connection refused")

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        report = perf_report.run("http://fake", "a@b.c", "pw", repeat=3)

    by_name = {r["scenario"]: r for r in report["results"]}
    login = by_name["auth_login"]
    assert login["status"] == "failed"
    assert login["observations"] == 3
    assert login["failures"] == 3
    assert login["median_ms"] is None
    assert any("connection failed" in e or "login failed" in e for e in login["sample_errors"])
    # Queue retrieval doesn't depend on login succeeding -- it should also
    # fail cleanly, not be skipped or crash the run.
    assert by_name["queue_retrieval"]["status"] == "failed"
    # Downstream of the (also-failing) pack lookup -- skipped, not crashed.
    assert by_name["assessment_bootstrap_register_plus_create"]["status"] == "skipped"


def test_http_error_response_is_reported_with_status_and_detail():
    class FakeHTTPError(urllib.error.HTTPError):
        def read(self):
            return json.dumps({"detail": "incorrect email or password"}).encode()

    def handler(method, url):
        if url.endswith("/auth/login"):
            raise FakeHTTPError(url, 401, "Unauthorized", {}, None)
        return FakeResponse(200, [])

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        report = perf_report.run("http://fake", "a@b.c", "wrong-password", repeat=2)

    login = next(r for r in report["results"] if r["scenario"] == "auth_login")
    assert login["status"] == "failed"
    assert any("incorrect email or password" in e or "status=401" in e for e in login["sample_errors"])


def test_a_500_response_is_a_failure_not_a_fast_success():
    """The real bug this guards against: queue_retrieval and
    rubric_retrieval used to time the call and report `ok=True` as soon as
    `client.call()` returned *anything* -- including a 500/401/404 -- since
    nothing checked the returned status. An error response that happens to
    come back quickly was silently counted as a fast successful
    observation."""

    def handler(method, url):
        if url.endswith("/auth/login"):
            return FakeResponse(200, {"access_token": "tok"})
        if url.endswith("/queue"):
            return FakeResponse(500, {"detail": "internal server error"})
        if "packs/by-code" in url:
            return FakeResponse(200, {"pack_id": 1})
        if url.endswith("/workers/register"):
            return FakeResponse(200, {"worker_id": 1})
        if url.endswith("/assessments"):
            return FakeResponse(201, {"id": 42})
        if url.endswith("/rubric"):
            return FakeResponse(403, {"detail": "forbidden"})
        raise AssertionError(f"unexpected call: {method} {url}")

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        report = perf_report.run("http://fake", "a@b.c", "pw", repeat=4)

    by_name = {r["scenario"]: r for r in report["results"]}
    assert by_name["queue_retrieval"]["status"] == "failed"
    assert by_name["queue_retrieval"]["failures"] == 4
    assert by_name["queue_retrieval"]["median_ms"] is None
    assert any("500" in e for e in by_name["queue_retrieval"]["sample_errors"])
    assert by_name["rubric_retrieval"]["status"] == "failed"
    assert any("403" in e for e in by_name["rubric_retrieval"]["sample_errors"])


def test_main_never_crashes_and_always_writes_a_report(tmp_path):
    """End-to-end through main(): even total backend unavailability must
    exit cleanly (no raised exception escapes main()) and leave a valid
    JSON file at --out."""

    def handler(method, url):
        raise urllib.error.URLError("Connection refused")

    out_path = tmp_path / "perf.json"
    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        exit_code = perf_report.main([
            "--base-url", "http://fake",
            "--assessor-email", "a@b.c",
            "--assessor-password", "pw",
            "--repeat", "2",
            "--out", str(out_path),
        ])

    assert exit_code == 0
    written = json.loads(out_path.read_text())
    assert written["results"][0]["status"] == "failed"


def test_main_reports_a_clean_error_if_the_output_path_is_unwritable():
    def handler(method, url):
        return FakeResponse(200, {"access_token": "tok"}) if url.endswith("/auth/login") else FakeResponse(200, [])

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        exit_code = perf_report.main([
            "--base-url", "http://fake",
            "--assessor-email", "a@b.c",
            "--assessor-password", "pw",
            "--repeat", "1",
            "--out", "/nonexistent-directory-xyz/perf.json",
        ])

    assert exit_code == 1

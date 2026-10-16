"""Regression tests for tools/perf_upload.py's error-handling contract
(same as tools/perf_report.py -- see that module's test file for the
rationale). Mocks urllib.request.urlopen; no real Docker/network needed.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import perf_upload  # noqa: E402


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
    def fake_urlopen(req, timeout=120):
        return handler(req.get_method(), req.full_url)

    return fake_urlopen


def test_missing_pack_skips_every_scenario_gracefully():
    def handler(method, url):
        if "packs/by-code" in url:
            return FakeResponse(404, {"detail": "no imported pack"})
        raise AssertionError(f"unexpected call: {method} {url}")

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        report = perf_upload.run("http://fake", repeat=2, photo_bytes=1024, video_bytes=0, chunk_bytes=65536)

    assert all(r["status"] == "skipped" for r in report["results"])
    assert "no imported pack" in report["results"][0]["skip_reason"]


def test_successful_upload_flow_times_manifest_and_photo():
    sessions = {"counter": 0}

    def handler(method, url):
        if "packs/by-code" in url:
            return FakeResponse(200, {"pack_id": 1})
        if url.endswith("/workers/register"):
            return FakeResponse(200, {"worker_id": 7})
        if url.endswith("/assessments"):
            return FakeResponse(201, {"id": 42, "worker_token": "tok"})
        if url.endswith("/uploads"):
            sessions["counter"] += 1
            return FakeResponse(201, {"id": sessions["counter"]})
        if "/chunks/" in url:
            return FakeResponse(200, {"chunk_index": 0, "received_bytes": 1, "next_chunk_index": 1, "status": "open"})
        if url.endswith("/complete"):
            return FakeResponse(200, {"status": "received"})
        raise AssertionError(f"unexpected call: {method} {url}")

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        report = perf_upload.run("http://fake", repeat=3, photo_bytes=2048, video_bytes=0, chunk_bytes=1024)

    by_name = {r["scenario"]: r for r in report["results"]}
    assert by_name["manifest_verification"]["status"] == "ok"
    assert by_name["manifest_verification"]["observations"] == 3
    assert by_name["evidence_upload_verify_photo"]["status"] == "ok"
    assert by_name["evidence_upload_verify_photo"]["observations"] == 3


def test_a_rejected_chunk_mid_upload_is_a_failure_not_a_crash():
    """The real failure mode this guards against: the server rejecting an
    out-of-order or oversized chunk partway through a multi-chunk upload
    must be reported as a scenario failure, never an uncaught exception
    that kills the whole benchmarking run."""

    def handler(method, url):
        if "packs/by-code" in url:
            return FakeResponse(200, {"pack_id": 1})
        if url.endswith("/workers/register"):
            return FakeResponse(200, {"worker_id": 7})
        if url.endswith("/assessments"):
            return FakeResponse(201, {"id": 42, "worker_token": "tok"})
        if url.endswith("/uploads"):
            return FakeResponse(201, {"id": 1})
        if "/chunks/0" in url:
            return FakeResponse(200, {"chunk_index": 0, "received_bytes": 1024, "next_chunk_index": 1, "status": "open"})
        if "/chunks/1" in url:
            return FakeResponse(409, {"detail": "out-of-order chunk"})
        raise AssertionError(f"unexpected call: {method} {url}")

    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        report = perf_upload.run("http://fake", repeat=1, photo_bytes=2048, video_bytes=0, chunk_bytes=1024)

    manifest = next(r for r in report["results"] if r["scenario"] == "manifest_verification")
    assert manifest["status"] == "failed"
    assert any("out-of-order" in e or "409" in e for e in manifest["sample_errors"])


def test_main_never_crashes_on_a_fully_unreachable_server(tmp_path):
    import urllib.error

    def handler(method, url):
        raise urllib.error.URLError("Connection refused")

    out_path = tmp_path / "perf-upload.json"
    with patch("urllib.request.urlopen", _fake_urlopen_factory(handler)):
        exit_code = perf_upload.main(["--base-url", "http://fake", "--repeat", "1", "--out", str(out_path)])

    assert exit_code == 0
    written = json.loads(out_path.read_text())
    assert written["results"][0]["status"] == "skipped"

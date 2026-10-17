"""P10.3: real upload-verification timing against a live FastAPI +
PostgreSQL stack -- the gap tools/perf_report.py's docstring explicitly
excludes (manifest-signing/chunked-evidence-upload timing).

Uses the exact real P6 protocol: a real Android-Keystore-shaped
ECDSA-signed manifest (via tools/docker_e2e_smoke_p6.build_signed_manifest,
reused rather than reimplemented), and real sequential chunked uploads
through the same /uploads session/chunks/complete endpoints the Android
app and server/app/manifest_verify.py actually use -- not a single big PUT.
Chunk size defaults to 1 MiB, matching the Android client's real streamed
chunk size (see docs/gates/P6.md). Media bytes are genuinely random
(os.urandom), not all-zero, so chunk timing/throughput reflects real
non-compressible payload handling rather than an artificially
fast/slow degenerate case.

No assessor login is needed: POST /assessments and the worker-token-scoped
upload endpoints are deliberately open to any caller (see
docs/worker_capability_tokens.md) -- this tool only exercises the
worker-side upload path, never assessor review.

Error handling follows the same contract as tools/perf_report.py: a
connection failure or unexpected HTTP status is recorded as a scenario
failure with a sample error message, never an uncaught crash, and
`--throttle-bytes-per-second` degradation never produces a fabricated
number -- if the throttled run can't complete in --timeout seconds, that
is reported as a failure, not silently omitted or guessed at.

Usage:
    server/.venv/bin/python tools/perf_upload.py \
        --base-url http://127.0.0.1:18400 --repeat 5 --out /tmp/perf-upload.json

Usage with a throttled connection (reuses tools/p8_network_proxy.py's
loopback cap -- start that separately first, pointed at the real API):
    python3 tools/p8_network_proxy.py --upload-bytes-per-second 262144 &
    server/.venv/bin/python tools/perf_upload.py \
        --base-url http://127.0.0.1:18009 --repeat 1 --photo-bytes 1048576 \
        --video-bytes 0 --out /tmp/perf-upload-throttled.json
(p8_network_proxy.py forwards 127.0.0.1:18009 -> 127.0.0.1:18008, so the
API must actually be reachable at that fixed port for this combination --
see tools/perf_throttled_upload.py for a version that drives this
automatically against infra/docker-compose.p8-test.yml's fixed port.)
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tools.docker_e2e_smoke_p6 import build_signed_manifest  # noqa: E402
from tools.perf_report import _git_commit, skipped, summarize  # noqa: E402


class UploadClient:
    """Same error-handling contract as perf_report.Client: every failure
    mode (HTTP error, connection refused, timeout) comes back as a plain
    (status, body) tuple, never raises -- callers check status explicitly."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, *, json_body: dict | None = None,
              raw_body: bytes | None = None, worker_token: str | None = None) -> tuple[int, dict]:
        headers = {}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            data = raw_body
            headers["Content-Type"] = "application/octet-stream"
        if worker_token:
            headers["X-Worker-Token"] = worker_token
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, (json.loads(raw) if raw else {})
            except json.JSONDecodeError:
                return e.code, {"detail": raw[:300].decode(errors="replace")}
        except urllib.error.URLError as e:
            return 0, {"detail": f"connection failed: {getattr(e, 'reason', e)}"}


def expect(status: int, body, *, ok: tuple[int, ...], what: str):
    if status not in ok:
        raise RuntimeError(f"{what} failed: status={status} {body.get('detail', body) if isinstance(body, dict) else body}")
    return body


def chunked_upload(client: UploadClient, worker_token: str, session_id: int, data: bytes, chunk_bytes: int) -> None:
    for i, offset in enumerate(range(0, len(data), chunk_bytes)):
        chunk = data[offset:offset + chunk_bytes]
        status, body = client.call("PUT", f"/uploads/{session_id}/chunks/{i}", raw_body=chunk, worker_token=worker_token)
        expect(status, body, ok=(200,), what=f"chunk {i} upload")


def bootstrap_assessment(client: UploadClient, pack_id: int, unique: str) -> tuple[int, str]:
    status, worker = client.call("POST", "/workers/register", json_body={
        "device_worker_id": f"KP-PERFUPLOAD-{unique}", "display_name": "Perf Upload Worker",
    })
    worker = expect(status, worker, ok=(200,), what="worker registration")
    status, assessment = client.call("POST", "/assessments", json_body={"worker_id": worker["worker_id"], "pack_id": pack_id})
    assessment = expect(status, assessment, ok=(200, 201), what="assessment create")
    return assessment["id"], assessment["worker_token"]


def run(base_url: str, repeat: int, photo_bytes: int, video_bytes: int, chunk_bytes: int) -> dict:
    client = UploadClient(base_url)
    results = []

    status, pack_lookup = client.call("GET", "/packs/by-code?qp_code=CON%2FQ0602&qp_version=4.0")
    if status != 200:
        reason = (
            f"could not resolve the CON/Q0602 pack (status={status} {pack_lookup.get('detail', pack_lookup)}) "
            "-- import it first: python -m app.pack_import"
        )
        return _finalize(base_url, [
            skipped("manifest_verification", reason),
            skipped("evidence_upload_verify_photo", reason),
            skipped("evidence_upload_verify_video", reason),
        ], photo_bytes, video_bytes, chunk_bytes)
    pack_id = pack_lookup["pack_id"]

    manifest_samples, manifest_failures, manifest_errors = [], 0, []
    photo_samples, photo_failures, photo_errors = [], 0, []
    video_samples, video_failures, video_errors = [], 0, []

    for i in range(repeat):
        unique = f"{time.time_ns()}-{i}"
        try:
            aid, wt = bootstrap_assessment(client, pack_id, unique)
        except Exception as e:  # noqa: BLE001 -- see module docstring's error-handling contract
            manifest_failures += 1
            manifest_errors.append(f"bootstrap failed: {e}")
            photo_failures += 1
            video_failures += 1
            continue

        photo_data = os.urandom(photo_bytes) if photo_bytes else b""
        video_data = os.urandom(video_bytes) if video_bytes else b""
        revision_id = f"perf-upload-rev-{unique}"
        items = []
        task_totals = {}
        if photo_bytes:
            items.append({
                "evidenceId": "ev-t1", "taskId": "T1", "kind": "photo", "bytes": len(photo_data),
                "sha256": hashlib.sha256(photo_data).hexdigest(), "mimeType": "image/jpeg", "processing": "SEALED",
            })
            task_totals["T1"] = len(photo_data)
        if video_bytes:
            items.append({
                "evidenceId": "ev-t2", "taskId": "T2", "kind": "video", "bytes": len(video_data),
                "sha256": hashlib.sha256(video_data).hexdigest(), "mimeType": "video/mp4", "processing": "SEALED",
            })
            task_totals["T2"] = len(video_data)
        total_bytes = len(photo_data) + len(video_data)
        envelope_bytes, _canonical, _key = build_signed_manifest(aid, revision_id, items, task_totals, total_bytes)

        # ---- manifest_verification: open+chunk+complete for the signed manifest envelope ----
        start = time.perf_counter()
        try:
            status, session = client.call("POST", "/uploads", worker_token=wt, json_body={
                "assessment_id": aid, "claimed_size_bytes": len(envelope_bytes),
                "target": "manifest", "revision_id": revision_id,
            })
            session = expect(status, session, ok=(201,), what="manifest session open")
            chunked_upload(client, wt, session["id"], envelope_bytes, chunk_bytes)
            status, receipt = client.call(
                "POST", f"/uploads/{session['id']}/complete", worker_token=wt,
                json_body={"client_sha256": hashlib.sha256(envelope_bytes).hexdigest()},
            )
            expect(status, receipt, ok=(200,), what="manifest complete/verify")
            manifest_samples.append((time.perf_counter() - start) * 1000)
        except Exception as e:  # noqa: BLE001
            manifest_failures += 1
            manifest_errors.append(str(e))
            continue  # evidence uploads need a verified manifest first

        # ---- evidence_upload_verify_photo ----
        if photo_bytes:
            start = time.perf_counter()
            try:
                status, session = client.call("POST", "/uploads", worker_token=wt, json_body={
                    "assessment_id": aid, "claimed_size_bytes": len(photo_data), "target": "evidence",
                    "task_code": "T1", "kind": "photo", "mime": "image/jpeg",
                    "revision_id": revision_id, "client_evidence_id": "ev-t1",
                })
                session = expect(status, session, ok=(201,), what="photo session open")
                chunked_upload(client, wt, session["id"], photo_data, chunk_bytes)
                status, receipt = client.call(
                    "POST", f"/uploads/{session['id']}/complete", worker_token=wt,
                    json_body={"client_sha256": hashlib.sha256(photo_data).hexdigest()},
                )
                expect(status, receipt, ok=(200,), what="photo complete/verify")
                photo_samples.append((time.perf_counter() - start) * 1000)
            except Exception as e:  # noqa: BLE001
                photo_failures += 1
                photo_errors.append(str(e))

        # ---- evidence_upload_verify_video ----
        if video_bytes:
            start = time.perf_counter()
            try:
                status, session = client.call("POST", "/uploads", worker_token=wt, json_body={
                    "assessment_id": aid, "claimed_size_bytes": len(video_data), "target": "evidence",
                    "task_code": "T2", "kind": "video", "mime": "video/mp4",
                    "revision_id": revision_id, "client_evidence_id": "ev-t2",
                })
                session = expect(status, session, ok=(201,), what="video session open")
                chunked_upload(client, wt, session["id"], video_data, chunk_bytes)
                status, receipt = client.call(
                    "POST", f"/uploads/{session['id']}/complete", worker_token=wt,
                    json_body={"client_sha256": hashlib.sha256(video_data).hexdigest()},
                )
                expect(status, receipt, ok=(200,), what="video complete/verify")
                video_samples.append((time.perf_counter() - start) * 1000)
            except Exception as e:  # noqa: BLE001
                video_failures += 1
                video_errors.append(str(e))

    results = []
    if photo_bytes:
        results.append(summarize("manifest_verification", manifest_samples, manifest_failures, manifest_errors))
        results.append(summarize("evidence_upload_verify_photo", photo_samples, photo_failures, photo_errors))
    if video_bytes:
        if not photo_bytes:
            results.append(summarize("manifest_verification", manifest_samples, manifest_failures, manifest_errors))
        results.append(summarize("evidence_upload_verify_video", video_samples, video_failures, video_errors))
    return _finalize(base_url, results, photo_bytes, video_bytes, chunk_bytes)


def _finalize(base_url: str, results: list[dict], photo_bytes: int, video_bytes: int, chunk_bytes: int) -> dict:
    return {
        "provenance": {
            "source_commit": _git_commit(),
            "base_url": base_url,
            "photo_bytes": photo_bytes,
            "video_bytes": video_bytes,
            "chunk_bytes": chunk_bytes,
            "measurement_kind": (
                "real chunked upload through the real P6 /uploads protocol with a real "
                "ECDSA-signed manifest and real (os.urandom) media bytes; not synthetic, not mocked"
            ),
        },
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--photo-bytes", type=int, default=2 * 1024 * 1024, help="0 to skip the photo scenario")
    parser.add_argument("--video-bytes", type=int, default=8 * 1024 * 1024, help="0 to skip the video scenario")
    parser.add_argument("--chunk-bytes", type=int, default=1024 * 1024, help="matches the Android client's real streamed chunk size")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        report = run(args.base_url, args.repeat, args.photo_bytes, args.video_bytes, args.chunk_bytes)
    except Exception as e:  # noqa: BLE001 -- last-resort safety net, see perf_report.py's identical contract
        print(f"perf_upload.py: unexpected failure, no report produced: {e}", file=sys.stderr)
        return 1

    try:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
    except OSError as e:
        print(f"perf_upload.py: could not write --out {args.out!r}: {e}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""P10.3: backend performance benchmarking against a real running FastAPI +
PostgreSQL stack (e.g. infra/docker-compose.yml or infra/docker-compose.p8-test.yml).

Real HTTP calls only -- no mocked responses, no synthetic timing. Each
scenario is repeated `--repeat` times and reported as count/median/p95/
min/max/failures, with explicit provenance (source commit, timestamp,
target base URL, scenario) so results are never presented without context.

Error handling contract (P10 fix): a single unreachable server, an
unimported pack, or any other mid-run failure must never crash this script
with a raw traceback and zero output. Every HTTP-level failure (4xx/5xx)
AND every connection-level failure (refused/timeout/DNS) is captured as a
normal, reportable outcome. A stage whose prerequisite failed (e.g. the
pack lookup, which every later stage depends on) is marked "skipped" with
an explicit reason rather than silently showing "0 observations, 0
failures" (which would be indistinguishable from "nothing to measure
here"). `main()` always writes whatever was collected to `--out`, even if
an individual stage blew up unexpectedly; only a failure to parse
arguments or write the output file itself is a hard, nonzero-exit error.

This tool intentionally measures backend request/response latency only.
Manifest-signing/chunked-evidence-upload timing is covered separately by
tools/perf_upload.py (real Android-Keystore-shaped signed manifest +
chunked upload, timed) and throttled-network timing by
tools/perf_upload.py's --throttle-bytes-per-second option (reusing
tools/p8_network_proxy.py's loopback cap); Android and dashboard-browser
timing are reported separately in docs/perf.md, each labelled by its own
actual source. Do not read a measurement from this tool as covering those.

Usage:
    server/.venv/bin/python tools/perf_report.py \
        --base-url http://127.0.0.1:18100 \
        --assessor-email p10-perf@parakh.test --assessor-password p10-perf-isolated-test-only \
        --repeat 20 --out /tmp/perf-backend.json
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


class Client:
    """Every failure mode -- an HTTP error response, a refused/reset
    connection, a DNS failure, a timeout -- comes back as a plain
    (status, body) tuple instead of raising. status=0 marks a
    connection-level failure (never a real HTTP status); body always has a
    "detail" string. Callers use the exact same `if status != expected`
    check for both kinds of failure -- one code path, not two."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return resp.status, (self._parse(raw))
        except urllib.error.HTTPError as e:
            return e.code, self._parse(e.read())
        except urllib.error.URLError as e:
            # Connection refused, DNS failure, timeout, etc. -- the server
            # is not reachable at all, which is a reportable measurement
            # outcome (the backend is down), not a reason to crash the
            # whole benchmarking run.
            return 0, {"detail": f"connection failed: {e.reason if hasattr(e, 'reason') else e}"}

    @staticmethod
    def _parse(raw: bytes) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"detail": f"non-JSON response body ({len(raw)} bytes)"}


def timed(fn) -> tuple[float, bool, str | None]:
    start = time.perf_counter()
    try:
        fn()
        return (time.perf_counter() - start) * 1000, True, None
    except Exception as e:  # noqa: BLE001 -- a benchmark records the failure, not the traceback
        return (time.perf_counter() - start) * 1000, False, str(e)


def summarize(name: str, samples_ms: list[float], failures: int, errors: list[str] | None = None) -> dict:
    ok = samples_ms
    if ok and failures == 0:
        status = "ok"
    elif ok and failures > 0:
        status = "degraded"
    elif not ok and failures > 0:
        status = "failed"
    else:
        status = "no_data"  # 0 observations, 0 failures -- should not normally occur; see skipped()
    # Up to 3 distinct sample error messages -- enough to diagnose WHY a
    # scenario failed (wrong credentials vs. connection refused vs. a 500)
    # without dumping every one of `--repeat` identical failures.
    sample_errors = list(dict.fromkeys(errors or []))[:3]
    return {
        "scenario": name,
        "status": status,
        "observations": len(ok) + failures,
        "failures": failures,
        "median_ms": round(statistics.median(ok), 2) if ok else None,
        "p95_ms": round(statistics.quantiles(ok, n=20)[18], 2) if len(ok) >= 5 else (round(max(ok), 2) if ok else None),
        "min_ms": round(min(ok), 2) if ok else None,
        "max_ms": round(max(ok), 2) if ok else None,
        "sample_errors": sample_errors,
        "provenance": "real HTTP call against a live FastAPI+PostgreSQL stack",
    }


def skipped(name: str, reason: str) -> dict:
    """A scenario that was never attempted because an earlier prerequisite
    (e.g. the pack lookup every later scenario depends on) failed. Kept
    structurally distinct from summarize()'s "0 observations, 0 failures"
    shape so a reader can't mistake "we didn't even try" for "we tried and
    there was nothing to measure"."""
    return {
        "scenario": name,
        "status": "skipped",
        "observations": 0,
        "failures": 0,
        "median_ms": None,
        "p95_ms": None,
        "min_ms": None,
        "max_ms": None,
        "sample_errors": [],
        "skip_reason": reason,
        "provenance": "real HTTP call against a live FastAPI+PostgreSQL stack",
    }


def expect(status: int, body, *, ok: tuple[int, ...] = (200,), what: str):
    """Every call site must route its result through this, not just time()
    the call and move on -- a bare `client.call(...)` with no status check
    silently reports an error response as a "successful" (and
    deceptively fast) observation, since Client.call() returns failures
    rather than raising them. This is the second real bug this file's
    error-handling fix closes: queue_retrieval/rubric_retrieval previously
    had no status check at all."""
    if status not in ok:
        raise RuntimeError(f"{what} failed: status={status} {body.get('detail', body)}")
    return body


def _run_repeated(repeat: int, fn) -> tuple[list[float], int, list[str]]:
    samples, failures, errors = [], 0, []
    for _ in range(repeat):
        ms, ok, err = timed(fn)
        if ok:
            samples.append(ms)
        else:
            failures += 1
            if err:
                errors.append(err)
    return samples, failures, errors


def run(base_url: str, email: str, password: str, repeat: int) -> dict:
    client = Client(base_url)
    results = []

    # ---- login ----
    def do_login():
        status, body = client.call("POST", "/auth/login", {"email": email, "password": password})
        body = expect(status, body, what="login")
        client.token = body["access_token"]

    login_samples, login_failures, login_errors = _run_repeated(repeat, do_login)
    results.append(summarize("auth_login", login_samples, login_failures, login_errors))

    # Bootstrap: resolve the imported pack once (not timed -- this is
    # setup). Every later stage needs pack_id; if this fails (pack not
    # imported yet, or the server became unreachable after login), those
    # stages are marked "skipped" below instead of this function raising
    # and discarding the login/queue results already collected above.
    pack_id = None
    pack_lookup_error = None
    try:
        status, pack_lookup = client.call("GET", "/packs/by-code?qp_code=CON%2FQ0602&qp_version=4.0")
        if status != 200:
            pack_lookup_error = (
                f"could not resolve the CON/Q0602 pack (status={status} {pack_lookup.get('detail', pack_lookup)}) "
                "-- import it first: python -m app.pack_import"
            )
        else:
            pack_id = pack_lookup["pack_id"]
    except Exception as e:  # noqa: BLE001 -- see module docstring's error-handling contract
        pack_lookup_error = f"pack lookup raised an unexpected error: {e}"

    # ---- queue retrieval (independent of pack_id) ----
    def do_queue():
        status, body = client.call("GET", "/queue")
        # A 200 body is a JSON array (QueueItemOut[]); an error body is a
        # dict ({"detail": ...}) -- expect() only touches .get() on the
        # error path, so this is safe either way.
        expect(status, body, what="queue retrieval")

    queue_samples, queue_failures, queue_errors = _run_repeated(repeat, do_queue)
    results.append(summarize("queue_retrieval", queue_samples, queue_failures, queue_errors))

    if pack_id is None:
        results.append(skipped("assessment_bootstrap_register_plus_create", pack_lookup_error))
        results.append(skipped("rubric_retrieval", pack_lookup_error))
        return _finalize(base_url, results)

    # ---- assessment bootstrap (worker self-registration + create) ----
    created_ids: list[int] = []
    counter = {"i": 0}

    def do_bootstrap():
        counter["i"] += 1
        status, worker = client.call(
            "POST", "/workers/register",
            {"device_worker_id": f"KP-PERF-{time.time_ns()}-{counter['i']}", "display_name": "Perf Worker"},
        )
        worker = expect(status, worker, what="worker registration")
        status, assessment = client.call("POST", "/assessments", {"worker_id": worker["worker_id"], "pack_id": pack_id})
        assessment = expect(status, assessment, ok=(200, 201), what="assessment create")
        created_ids.append(assessment["id"])

    bootstrap_samples, bootstrap_failures, bootstrap_errors = _run_repeated(repeat, do_bootstrap)
    results.append(summarize("assessment_bootstrap_register_plus_create", bootstrap_samples, bootstrap_failures, bootstrap_errors))

    # ---- rubric retrieval (reuses the first bootstrapped assessment) ----
    if not created_ids:
        results.append(skipped(
            "rubric_retrieval",
            "assessment_bootstrap_register_plus_create produced no assessment to read a rubric from "
            f"(see its sample_errors: {bootstrap_errors[:1]})",
        ))
    else:
        target_id = created_ids[0]

        def do_rubric():
            status, body = client.call("GET", f"/assessments/{target_id}/rubric")
            expect(status, body, what="rubric retrieval")

        rubric_samples, rubric_failures, rubric_errors = _run_repeated(repeat, do_rubric)
        results.append(summarize("rubric_retrieval", rubric_samples, rubric_failures, rubric_errors))

    return _finalize(base_url, results)


def _finalize(base_url: str, results: list[dict]) -> dict:
    return {
        "provenance": {
            "source_commit": _git_commit(),
            "generated_at_note": "caller must stamp wall-clock time -- see docs/perf.md",
            "base_url": base_url,
            "measurement_kind": "real HTTP latency against a live backend; not synthetic, not mocked",
        },
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--assessor-email", required=True)
    parser.add_argument("--assessor-password", required=True)
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        report = run(args.base_url, args.assessor_email, args.assessor_password, args.repeat)
    except Exception as e:  # noqa: BLE001 -- last-resort safety net; run() already handles every
        # known failure mode internally (see module docstring). This only
        # catches something truly unanticipated, and still tries to leave
        # a diagnostic trace instead of a bare traceback.
        print(f"perf_report.py: unexpected failure, no report produced: {e}", file=sys.stderr)
        return 1

    try:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
    except OSError as e:
        print(f"perf_report.py: could not write --out {args.out!r}: {e}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

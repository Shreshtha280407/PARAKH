"""P10.3: backend performance benchmarking against a real running FastAPI +
PostgreSQL stack (e.g. infra/docker-compose.yml or infra/docker-compose.p8-test.yml).

Real HTTP calls only -- no mocked responses, no synthetic timing. Each
scenario is repeated `--repeat` times and reported as count/median/p95/
min/max/failures, with explicit provenance (source commit, timestamp,
target base URL, scenario) so results are never presented without context.

This tool intentionally measures backend request/response latency only.
Manifest-signing/chunked-evidence-upload timing is NOT covered here (it
requires reproducing P5's Android-Keystore-ECDSA-signed manifest format,
real media files, and the resumable chunk protocol -- see
tools/docker_e2e_smoke_p6.py for the functional, not timed, version of that
flow); Android, dashboard-browser and real-network timing are reported
separately in docs/perf.md, each labelled by its own actual source. Do not
read a measurement from this tool as covering those.

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
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            return e.code, (json.loads(raw) if raw else {})


def timed(fn) -> tuple[float, bool, str | None]:
    start = time.perf_counter()
    try:
        fn()
        return (time.perf_counter() - start) * 1000, True, None
    except Exception as e:  # noqa: BLE001 -- a benchmark records the failure, not the traceback
        return (time.perf_counter() - start) * 1000, False, str(e)


def summarize(name: str, samples_ms: list[float], failures: int) -> dict:
    ok = [s for s in samples_ms]
    return {
        "scenario": name,
        "observations": len(ok) + failures,
        "failures": failures,
        "median_ms": round(statistics.median(ok), 2) if ok else None,
        "p95_ms": round(statistics.quantiles(ok, n=20)[18], 2) if len(ok) >= 5 else (round(max(ok), 2) if ok else None),
        "min_ms": round(min(ok), 2) if ok else None,
        "max_ms": round(max(ok), 2) if ok else None,
        "provenance": "real HTTP call against a live FastAPI+PostgreSQL stack",
    }


def run(base_url: str, email: str, password: str, repeat: int) -> dict:
    client = Client(base_url)
    results = []

    # ---- login ----
    login_samples, login_failures = [], 0
    for _ in range(repeat):
        holder = {}

        def do_login():
            status, body = client.call("POST", "/auth/login", {"email": email, "password": password})
            if status != 200:
                raise RuntimeError(f"login failed: {status} {body}")
            holder["token"] = body["access_token"]

        ms, ok, _ = timed(do_login)
        if ok:
            login_samples.append(ms)
            client.token = holder["token"]
        else:
            login_failures += 1
    results.append(summarize("auth_login", login_samples, login_failures))

    # Bootstrap: resolve the imported pack once (not timed -- this is setup).
    status, pack_lookup = client.call("GET", "/packs/by-code?qp_code=CON%2FQ0602&qp_version=4.0")
    if status != 200:
        raise RuntimeError(f"could not resolve the CON/Q0602 pack -- import it first (python -m app.pack_import): {status} {pack_lookup}")
    pack_id = pack_lookup["pack_id"]

    # ---- queue retrieval ----
    queue_samples, queue_failures = [], 0
    for _ in range(repeat):
        ms, ok, _ = timed(lambda: client.call("GET", "/queue"))
        if ok:
            queue_samples.append(ms)
        else:
            queue_failures += 1
    results.append(summarize("queue_retrieval", queue_samples, queue_failures))

    # ---- assessment bootstrap (worker self-registration + create) ----
    bootstrap_samples, bootstrap_failures = [], 0
    created_ids = []
    for i in range(repeat):
        holder = {}

        def do_bootstrap():
            status, worker = client.call(
                "POST", "/workers/register", {"device_worker_id": f"KP-PERF-{time.time_ns()}-{i}", "display_name": "Perf Worker"}
            )
            if status != 200:
                raise RuntimeError(f"register failed: {status} {worker}")
            status, assessment = client.call("POST", "/assessments", {"worker_id": worker["worker_id"], "pack_id": pack_id})
            if status not in (200, 201):
                raise RuntimeError(f"assessment create failed: {status} {assessment}")
            holder["id"] = assessment["id"]

        ms, ok, _ = timed(do_bootstrap)
        if ok:
            bootstrap_samples.append(ms)
            created_ids.append(holder["id"])
        else:
            bootstrap_failures += 1
    results.append(summarize("assessment_bootstrap_register_plus_create", bootstrap_samples, bootstrap_failures))

    # ---- rubric retrieval (reuses the first bootstrapped assessment) ----
    rubric_samples, rubric_failures = [], 0
    target_id = created_ids[0] if created_ids else None
    if target_id is not None:
        for _ in range(repeat):
            ms, ok, _ = timed(lambda: client.call("GET", f"/assessments/{target_id}/rubric"))
            if ok:
                rubric_samples.append(ms)
            else:
                rubric_failures += 1
    results.append(summarize("rubric_retrieval", rubric_samples, rubric_failures))

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

    report = run(args.base_url, args.assessor_email, args.assessor_password, args.repeat)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

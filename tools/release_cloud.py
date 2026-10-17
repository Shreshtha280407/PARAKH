#!/usr/bin/env python3
"""Release the reviewed checkout, retaining existing services and provider config.

No source integrations, service creation, secret writes, data cleanup or schema
downgrades. Capture only allowlisted deployment metadata, never variable values.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import io
import tarfile
import tempfile
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
TARGET = json.loads((ROOT / "infra/hosting-target.json").read_text())
SHA = os.environ.get("RELEASE_SHA", "")


def command(args, cwd=ROOT, env=None):
    if args[0] == "vercel" and "--token" not in args and os.environ.get("VERCEL_TOKEN"):
        args = [*args, "--token", os.environ["VERCEL_TOKEN"]]
    result = subprocess.run(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1200)
    if result.returncode:
        # Raw provider output can contain environment values and signed URLs.
        raise RuntimeError(f"{args[0]} {args[1]} failed; inspect the provider's protected logs")
    return result.stdout


def railway_args(service):
    return ["--project", TARGET["railway_project"], "--environment", TARGET["railway_environment"], "--service", service]


def preflight():
    if len(SHA) != 40 or command(["git", "rev-parse", "HEAD"]).strip() != SHA:
        raise RuntimeError("checkout does not match the CI-approved SHA")
    for key in ("RAILWAY_TOKEN", "VERCEL_TOKEN", "NEON_DIRECT_DATABASE_URL"):
        if not os.environ.get(key):
            raise RuntimeError(f"missing encrypted secret {key}")
    from sqlalchemy.engine import make_url
    if make_url(os.environ["NEON_DIRECT_DATABASE_URL"]).host != TARGET["neon_direct_host"]:
        raise RuntimeError("migration endpoint differs from reviewed staging endpoint")
    for service in (TARGET["railway_api_service"], TARGET["railway_worker_service"]):
        variables = json.loads(command(["railway", "variable", "list", *railway_args(service), "--json"]))
        host = make_url(variables["DATABASE_URL"]).host.replace("-pooler", "")
        if host != TARGET["neon_direct_host"] or variables.get("S3_BUCKET") != TARGET["s3_bucket"]:
            raise RuntimeError("runtime database/storage differs from reviewed staging target")
        if TARGET["neon_branch"] not in variables.get("S3_ENDPOINT_URL", ""):
            raise RuntimeError("runtime storage branch mismatch")
        if variables.get("RAILWAY_DOCKERFILE_PATH") != "server/Dockerfile":
            raise RuntimeError("Railway Dockerfile must be server/Dockerfile with repository root context")
    project = json.loads(command(["vercel", "api", f"/v9/projects/{TARGET['vercel_project']}"]))
    if project.get("link"):
        raise RuntimeError("disable native Vercel Git deployment before using the coordinated release")
    if project.get("rootDirectory") is not None:
        raise RuntimeError("unexpected Vercel root directory")
    status = json.loads(command(["railway", "status", "--json", "--project", TARGET["railway_project"],
                                "--environment", TARGET["railway_environment"]]))
    instances = [edge["node"] for env in status["environments"]["edges"] if env["node"]["id"] == TARGET["railway_environment"]
                 for edge in env["node"]["serviceInstances"]["edges"]]
    expected_services = {TARGET["railway_api_service"], TARGET["railway_worker_service"]}
    if not expected_services.issubset({instance["serviceId"] for instance in instances}):
        raise RuntimeError("existing API or worker service is missing from the reviewed environment")
    for instance in instances:
        if instance["serviceId"] in (TARGET["railway_api_service"], TARGET["railway_worker_service"]):
            if instance.get("source", {}).get("repo"):
                raise RuntimeError("disconnect native Railway source before coordinated release")
            expected = "python -m app.worker" if instance["serviceId"] == TARGET["railway_worker_service"] else "uvicorn app.main:app --host 0.0.0.0 --port 8000"
            if instance.get("startCommand") != expected:
                raise RuntimeError("Railway start command drift detected")
            meta = (instance.get("latestDeployment") or {}).get("meta", {})
            deploy_config = meta.get("serviceManifest", {}).get("deploy", {})
            if meta.get("rootDirectory") not in (None, "", "/") or deploy_config.get("preDeployCommand"):
                raise RuntimeError("Railway build root or migration ownership drift detected")
    print("Preflight passed: exact SHA, staging database/storage, existing services, no conflicting Git deployment")


@contextmanager
def railway_build_context():
    # The CLI normally omits gitignored files, including the generated SHA.
    # Export only the approved commit into a temporary context before explicitly
    # including ignored files. Local .env files and untracked credentials can
    # therefore never enter the upload. Keep the repository root build layout.
    archive = subprocess.run(["git", "archive", "--format=tar", SHA], cwd=ROOT,
                             capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory(prefix="parakh-release-") as directory:
        context = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(context, filter="data")
        (context / "server/app/source_version.json").write_text(json.dumps({"source_sha": SHA}))
        yield context


def deploy_railway(service, build_context):
    before = json.loads(command(["railway", "deployment", "list", *railway_args(service), "--limit", "5", "--json"]))
    previous = [row["id"] for row in before if row["status"] == "SUCCESS"]
    (ROOT / f"previous-{service}.json").write_text(json.dumps(previous))
    command(["railway", "up", ".", *railway_args(service), "--path-as-root", "--no-gitignore",
             "--detach", "--message", f"github:{SHA}"], cwd=build_context)
    previous_ids = {row["id"] for row in before}
    for _ in range(120):
        rows = json.loads(command(["railway", "deployment", "list", *railway_args(service), "--limit", "5", "--json"]))
        current = [row for row in rows if row["id"] not in previous_ids]
        if current:
            row = current[0]
            if row["status"] in ("FAILED", "CRASHED", "REMOVED"):
                raise RuntimeError(f"Railway deployment {row['id']} failed; previous deployment IDs recorded")
            if row["status"] == "SUCCESS":
                return {"id": row["id"], "service": service, "source_sha": SHA}
        time.sleep(10)
    raise RuntimeError("Railway deployment health deadline exceeded")


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def verify_live():
    for origin, path in ((TARGET["api_url"], "/health"), (TARGET["dashboard_url"], "/api/health")):
        health = get_json(origin + path)
        if health.get("source_sha") != SHA or health.get("worker_source_sha") != SHA or any(health.get(k) != "ok" for k in ("status", "database", "storage")):
            raise RuntimeError("live health/source SHA mismatch")
    if get_json(TARGET["dashboard_url"] + "/version.json").get("source_sha") != SHA:
        raise RuntimeError("frontend source SHA mismatch")
    get_json(TARGET["dashboard_url"] + "/api/public/assessments?limit=1")
    print("Live health, same-origin API, public projection and frontend/API source SHA passed")


def deploy():
    results = []
    # SOURCE_SHA is built into each image, without changing platform variables or keys.
    with railway_build_context() as build_context:
        for service in (TARGET["railway_api_service"], TARGET["railway_worker_service"]):
            results.append(deploy_railway(service, build_context))
    env = {**os.environ, "VERCEL_ORG_ID": TARGET["vercel_org"], "VERCEL_PROJECT_ID": TARGET["vercel_project"],
           "VITE_API_BASE_URL": "/api", "VITE_SOURCE_SHA": SHA}
    dashboard = ROOT / "apps/dashboard"
    (dashboard / "public/version.json").write_text(json.dumps({"source_sha": SHA}))
    # Project root is null: CLI uploads apps/dashboard as root, matching the existing manual deployment.
    command(["vercel", "pull", "--yes", "--environment=production", "--token", env["VERCEL_TOKEN"]], dashboard, env)
    command(["vercel", "build", "--prod", "--token", env["VERCEL_TOKEN"]], dashboard, env)
    deployment_url = command(["vercel", "deploy", "--prebuilt", "--prod", "--token", env["VERCEL_TOKEN"]], dashboard, env).strip().splitlines()[-1]
    results.append({"provider": "vercel", "url": deployment_url, "source_sha": SHA})
    (ROOT / "deployment-result.json").write_text(json.dumps({"source_sha": SHA, "deployments": results}, indent=2))
    for attempt in range(12):
        try:
            verify_live()
            break
        except Exception:
            if attempt == 11:
                raise
            time.sleep(10)  # Wait for CDN alias propagation and the new worker heartbeat.


if __name__ == "__main__":
    try:
        {"preflight": preflight, "deploy": deploy, "verify": verify_live}[sys.argv[1]]()
    except Exception as error:
        if type(error) is RuntimeError:
            print(str(error))  # All RuntimeErrors above contain only allowlisted, secret-free diagnostics.
        print(f"Release failed ({type(error).__name__}). Preserve data and inspect protected provider logs; no automatic schema downgrade.")
        raise SystemExit(1)

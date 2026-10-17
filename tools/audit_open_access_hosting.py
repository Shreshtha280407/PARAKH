#!/usr/bin/env python3
"""Read-only hosting audit. Secret-bearing subprocess output never reaches logs.
Run from the repository root with the existing locally authenticated CLIs.
The optional gitignored .env.deploy supplies read-only database audit connections.
"""
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def cli(args):
    try:
        response = subprocess.run(args, text=True, capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        return {"audit_error": "provider request timed out"}
    if response.returncode:
        return {"audit_error": "provider unavailable or credentials need renewal"}
    try:
        return json.loads(response.stdout)
    except ValueError:
        return {"audit_error": "provider returned an unexpected response"}


def audit():
    output = {}
    target = json.loads((ROOT / "infra/hosting-target.json").read_text())
    scope = ["--project", target["railway_project"], "--environment", target["railway_environment"]]
    status = cli(["railway", "status", "--json", *scope])
    output["railway"] = []
    if "audit_error" in status:
        output["railway_audit_error"] = status["audit_error"]
    for environment in status.get("environments", {}).get("edges", []):
        for service in environment["node"]["serviceInstances"]["edges"]:
            item = service["node"]
            manifest = (item.get("latestDeployment") or {}).get("meta", {}).get("serviceManifest", {})
            variables = cli(["railway", "variable", "list", "--service", item["serviceId"], "--json", *scope])
            db = variables.get("DATABASE_URL", "")
            from sqlalchemy.engine import make_url
            host = make_url(db).host if db else None
            output["railway"].append({"service": item["serviceName"], "id": item["serviceId"], "source": item.get("source"),
                "environment": environment["node"]["name"], "start_command": item.get("startCommand"),
                "dockerfile": manifest.get("build", {}).get("dockerfilePath"),
                "root": (item.get("latestDeployment") or {}).get("meta", {}).get("rootDirectory"),
                "regions": manifest.get("deploy", {}).get("multiRegionConfig"),
                "migration_command": manifest.get("deploy", {}).get("preDeployCommand"),
                "variables_audit_error": variables.get("audit_error"),
                "database_host": host, "storage_bucket": variables.get("S3_BUCKET"),
                "storage_host": urlparse(variables.get("S3_ENDPOINT_URL", "")).hostname,
                "reviewer_mail_configured": None if "audit_error" in variables else bool(variables.get("REVIEWER_SMTP_HOST")),
                "signing_key_configured": None if "audit_error" in variables else bool(variables.get("REPORT_SIGNING_PRIVATE_KEY"))})
    vercel = cli(["vercel", "api", "/v9/projects/" + target["vercel_project"]])
    output["vercel"] = {key: vercel.get(key) for key in ("id", "name", "link", "rootDirectory", "framework", "buildCommand", "outputDirectory", "audit_error")}
    output["neon"] = cli(["neonctl", "branches", "list", "--project-id", "sparkling-band-45084780", "--output", "json"])
    values = {}
    config = ROOT / ".env.deploy"
    if config.exists():
        for line in config.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"').strip("'")
    for branch in ("STAGING", "MAIN"):
        url = values.get(branch + "_MIGRATION_DATABASE_URL")
        if not url:
            continue
        try:
            engine = create_engine(url, connect_args={"connect_timeout": 15})
            with engine.connect() as db:
                db.execute(text("SET TRANSACTION READ ONLY"))
                rows = db.execute(text("SELECT a.id, a.status, a.submitted_at, u.display_name, u.device_worker_id, "
                    "(SELECT count(*) FROM evidence_items e JOIN assessment_tasks t ON t.id=e.assessment_task_id WHERE t.assessment_id=a.id) AS evidence_count "
                    "FROM assessments a JOIN users u ON u.id=a.worker_id ORDER BY a.id")).mappings().all()
                output[branch.lower()] = {"schema": db.execute(text("SELECT version_num FROM alembic_version")).scalar(),
                    "assessments": [{"id": row["id"], "status": row["status"], "evidence_count": row["evidence_count"],
                        "identity_fingerprint": hashlib.sha256(f"{row['display_name']}:{row['device_worker_id']}".encode()).hexdigest()[:16],
                        "provenance": "requires owner verification; excluded from public listing"} for row in rows]}
            engine.dispose()
        except Exception as error:
            output[branch.lower()] = {"audit_error": "read-only database connection unavailable", "error_type": type(error).__name__}
    return output


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, default=str))

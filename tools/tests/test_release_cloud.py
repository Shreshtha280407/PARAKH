"""Fail-closed release preflight; no provider or credential writes in these tests."""
import importlib.util
import json
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_cloud", ROOT / "tools/release_cloud.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def setup_preflight(monkeypatch, *, source=None, database_host=None, vercel_link=None):
    sha = "a" * 40
    monkeypatch.setattr(release, "SHA", sha)
    for name in ("RAILWAY_TOKEN", "VERCEL_TOKEN", "NEON_DIRECT_DATABASE_URL"):
        monkeypatch.setenv(name, "test-only")
    monkeypatch.setenv("NEON_DIRECT_DATABASE_URL", f"postgresql+psycopg://test@{release.TARGET['neon_direct_host']}/test")
    calls = []

    def command(args, **kwargs):
        calls.append(args)
        if args[:2] == ["git", "rev-parse"]:
            return sha
        if args[:3] == ["railway", "variable", "list"]:
            return json.dumps({"DATABASE_URL": f"postgresql+psycopg://test@{database_host or release.TARGET['neon_direct_host']}/test",
                "S3_BUCKET": release.TARGET["s3_bucket"], "S3_ENDPOINT_URL": f"https://{release.TARGET['neon_branch']}.storage.neon.tech",
                "RAILWAY_DOCKERFILE_PATH": "server/Dockerfile"})
        if args[:2] == ["vercel", "api"]:
            return json.dumps({"rootDirectory": None, "link": vercel_link})
        if args[:2] == ["railway", "status"]:
            return json.dumps({"environments": {"edges": [{"node": {"id": release.TARGET["railway_environment"], "serviceInstances": {"edges": [
                {"node": {"serviceId": release.TARGET["railway_api_service"], "source": {"repo": source}, "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port 8000"}},
                {"node": {"serviceId": release.TARGET["railway_worker_service"], "source": {"repo": source}, "startCommand": "python -m app.worker"}}
            ]}}}]}})
        raise AssertionError("preflight attempted an unexpected command")

    monkeypatch.setattr(release, "command", command)
    return calls


def test_preflight_requires_existing_staging_settings_and_only_reads(monkeypatch):
    calls = setup_preflight(monkeypatch)
    release.preflight()
    assert all("up" not in args and "set" not in args and "deploy" not in args for args in calls)


@pytest.mark.parametrize("change", [{"source": "owner/repo"}, {"vercel_link": {"repo": "PARAKH"}}, {"database_host": "production.neon.tech"}])
def test_preflight_rejects_native_auto_deploy_or_silent_database_cutover(monkeypatch, change):
    setup_preflight(monkeypatch, **change)
    with pytest.raises(RuntimeError):
        release.preflight()


def test_preflight_rejects_missing_secret_or_wrong_sha(monkeypatch):
    setup_preflight(monkeypatch)
    monkeypatch.delenv("RAILWAY_TOKEN")
    with pytest.raises(RuntimeError, match="missing encrypted secret"):
        release.preflight()
    monkeypatch.setenv("RAILWAY_TOKEN", "test-only")
    monkeypatch.setattr(release, "SHA", "b" * 40)
    with pytest.raises(RuntimeError, match="checkout does not match"):
        release.preflight()


def test_railway_context_contains_only_approved_archive_and_generated_sha(monkeypatch, tmp_path):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as bundle:
        for name, data in {"server/app/main.py": b"approved source", "packs/pack.json": b"{}",
                           ".gitignore": b"server/app/source_version.json\n"}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    (tmp_path / ".env.deploy").write_text("private-local-secret")
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "SHA", "a" * 40)
    def exported(args, **kwargs):
        assert args == ["git", "archive", "--format=tar", "a" * 40]
        return SimpleNamespace(stdout=archive.getvalue())
    monkeypatch.setattr(release.subprocess, "run", exported)
    with release.railway_build_context() as context:
        assert (context / "packs/pack.json").is_file()
        assert not (context / ".env.deploy").exists()
        assert json.loads((context / "server/app/source_version.json").read_text())["source_sha"] == "a" * 40
    assert not context.exists()


@pytest.mark.parametrize(("stderr", "expected"), [
    ("Failed to upload code. File too large (48632514 bytes): private-payload", "upload too large (48632514 bytes)"),
    ("Failed to upload code with status code 413; token=private-payload", "provider HTTP 413"),
    ("error: unexpected argument '--bad-flag' found; private-payload", "unsupported CLI argument"),
    ("Unauthorized: private-payload", "provider authorization rejected"),
    ("request timed out; private-payload", "provider request timed out"),
    ("unknown private-payload", "provider command rejected"),
])
def test_command_classifies_failure_without_disclosing_provider_output(monkeypatch, stderr, expected):
    monkeypatch.setattr(release.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stderr=stderr, stdout="secret-stdout"))
    with pytest.raises(RuntimeError) as error:
        release.command(["railway", "up"])
    assert expected in str(error.value)
    assert "exit 1" in str(error.value)
    assert "private-payload" not in str(error.value)
    assert "secret-stdout" not in str(error.value)


def test_railway_upload_excludes_non_server_assets_and_preserves_version():
    ignored = (ROOT / ".railwayignore").read_text().splitlines()
    for path in ("apps/android", "ml", "docs", ".github"):
        assert path in ignored
    assert "server" not in ignored
    assert "tools" not in ignored
    assert "packs" not in ignored
    assert "server/app/source_version.json" not in ignored

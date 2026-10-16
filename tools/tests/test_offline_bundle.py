"""Regression tests for tools/offline_bundle.py's no-pull contract (see
that module's docstring): starting the offline stack must hard-fail
immediately if anything would require a network fetch, a short/corrupt
export tar must be caught before touching Docker at all, and every Docker
failure must surface as a clean one-line message, never a raw traceback.

Most tests here mock subprocess.run (no real Docker needed, fast, runs
anywhere). One real end-to-end round-trip (build, export, delete images,
reload, start with --no-build --pull never, confirm healthy) was performed
manually against a live Docker daemon during this P10 pass -- see
docs/gates/P10.md and docs/deployment/README.md for that evidence; it is
deliberately not re-run on every test invocation since it needs a real
Docker daemon and takes minutes, not milliseconds.
"""
import json
import sys
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import offline_bundle  # noqa: E402


def _make_tar(tmp_path: Path, image_tags: list[str]) -> Path:
    tar_path = tmp_path / "images.tar"
    manifest_json = tmp_path / "manifest.json"
    manifest_json.write_text(json.dumps([{"RepoTags": [tag]} for tag in image_tags]))
    with tarfile.open(tar_path, "w") as tf:
        tf.add(manifest_json, arcname="manifest.json")
    return tar_path


def test_read_tar_image_tags_normalizes_implicit_latest(tmp_path):
    tar_path = _make_tar(tmp_path, ["kaushalpramaan-mvp-api:latest", "postgres:16-alpine"])
    tags = offline_bundle.read_tar_image_tags(str(tar_path))
    assert tags == {"kaushalpramaan-mvp-api", "postgres:16-alpine"}


def test_read_tar_image_tags_rejects_a_tar_with_no_manifest(tmp_path):
    tar_path = tmp_path / "empty.tar"
    with tarfile.open(tar_path, "w"):
        pass
    with pytest.raises(offline_bundle.OfflineBundleError, match="manifest.json"):
        offline_bundle.read_tar_image_tags(str(tar_path))


def test_read_tar_image_tags_rejects_a_missing_file():
    with pytest.raises(offline_bundle.OfflineBundleError, match="not found"):
        offline_bundle.read_tar_image_tags("/no/such/path.tar")


def test_verify_rejects_a_tar_missing_a_required_image_before_touching_docker(tmp_path):
    """The real bug this guards against: a short/corrupt export (e.g. a
    build failed silently and `docker save` only captured 4 of 5 images)
    used to only surface as an obscure `docker compose up` failure. Now
    it's caught up front, with Docker never even invoked."""
    incomplete_tar = _make_tar(tmp_path, [
        "myproj-api:latest", "myproj-worker:latest", "myproj-dashboard:latest", "myproj-migrate:latest",
        # postgres:16-alpine deliberately missing
    ])
    with patch("tools.offline_bundle.run") as mock_run, patch("subprocess.run") as mock_subprocess_run:
        with pytest.raises(offline_bundle.OfflineBundleError, match="postgres:16-alpine"):
            offline_bundle.verify_bundle("myproj", str(incomplete_tar), "infra/docker-compose.yml", 60, teardown=False)
    mock_run.assert_not_called()
    mock_subprocess_run.assert_not_called()


def test_verify_passes_no_build_and_pull_never_to_docker_compose(tmp_path):
    """The actual no-pull fix: starting the offline stack must explicitly
    forbid Docker from pulling anything, not rely solely on --no-build
    (which only forbids *building*, and -- for the directly-referenced
    `db: image: postgres:16-alpine` service with no build step at all --
    doesn't by itself rule out a pull)."""
    complete_tar = _make_tar(tmp_path, [
        "myproj-api:latest", "myproj-worker:latest", "myproj-dashboard:latest", "myproj-migrate:latest",
        "postgres:16-alpine",
    ])
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return None

    with patch("tools.offline_bundle.run", side_effect=fake_run), \
         patch("tools.offline_bundle._service_health", return_value="healthy"):
        offline_bundle.verify_bundle("myproj", str(complete_tar), "infra/docker-compose.yml", 60, teardown=False)

    up_call = next(c for c in calls if "up" in c)
    assert "--no-build" in up_call
    assert "--pull" in up_call and "never" in up_call[up_call.index("--pull") + 1:up_call.index("--pull") + 2]
    load_call = next(c for c in calls if "load" in c)
    assert "-i" in load_call and str(complete_tar) in load_call


def test_verify_tears_down_on_health_check_timeout_when_requested(tmp_path):
    complete_tar = _make_tar(tmp_path, [
        "myproj-api:latest", "myproj-worker:latest", "myproj-dashboard:latest", "myproj-migrate:latest",
        "postgres:16-alpine",
    ])
    teardown_calls = []

    def fake_subprocess_run(cmd, **kwargs):
        if "down" in cmd:
            teardown_calls.append(cmd)
        return type("R", (), {"returncode": 0, "stdout": "unhealthy"})()

    with patch("tools.offline_bundle.run"), \
         patch("tools.offline_bundle._service_health", return_value="starting"), \
         patch("tools.offline_bundle.time.sleep"), \
         patch("subprocess.run", side_effect=fake_subprocess_run):
        with pytest.raises(offline_bundle.OfflineBundleError, match="did not become healthy"):
            offline_bundle.verify_bundle("myproj", str(complete_tar), "infra/docker-compose.yml", timeout_seconds=1, teardown=True)

    assert len(teardown_calls) == 1


def test_run_wraps_a_docker_failure_as_a_clean_error_not_a_traceback():
    import subprocess as sp

    with patch("subprocess.run", side_effect=sp.CalledProcessError(1, ["docker", "compose", "up"])):
        with pytest.raises(offline_bundle.OfflineBundleError, match="command failed"):
            offline_bundle.run(["docker", "compose", "up"])


def test_run_wraps_missing_docker_binary_as_a_clean_error():
    with patch("subprocess.run", side_effect=FileNotFoundError("no such file")):
        with pytest.raises(offline_bundle.OfflineBundleError, match="not installed"):
            offline_bundle.run(["docker", "--version"])


def test_main_verify_exits_cleanly_on_a_missing_tar(capsys):
    exit_code = offline_bundle.main(["verify", "--tar", "/no/such/file.tar"])
    assert exit_code == 1
    assert "FAILED" in capsys.readouterr().err


def test_main_export_exits_cleanly_when_docker_is_unavailable(capsys):
    with patch("subprocess.run", side_effect=FileNotFoundError("docker: not found")):
        exit_code = offline_bundle.main(["export", "--out", "/tmp/unused.tar"])
    assert exit_code == 1
    assert "FAILED" in capsys.readouterr().err


def test_export_rejects_its_own_short_output(tmp_path):
    """The real bug this guards against: if `docker save` silently wrote a
    tar missing one of the expected images (e.g. because a build step
    failed in a way that `check=True` didn't catch, or a race with another
    concurrent export under the same project name), export_bundle used to
    report success and hand the caller a tar that would only fail later,
    on the offline machine, with no network available to fix it."""
    out_tar = tmp_path / "out.tar"

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "save"]:
            # Simulate docker save writing a short tar (one image missing).
            with tarfile.open(out_tar, "w") as tf:
                manifest = tmp_path / "manifest.json"
                manifest.write_text(json.dumps([
                    {"RepoTags": ["proj-api:latest"]},
                    {"RepoTags": ["proj-worker:latest"]},
                ]))
                tf.add(manifest, arcname="manifest.json")
        return None

    with patch("tools.offline_bundle.run", side_effect=fake_run):
        with pytest.raises(offline_bundle.OfflineBundleError, match="missing"):
            offline_bundle.export_bundle("proj", str(out_tar), "infra/docker-compose.yml")

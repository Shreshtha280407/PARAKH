"""P10.2: build the PARAKH Docker Compose stack once while online, bundle
every image it actually needs at runtime (the four built images, plus
`postgres:16-alpine`, which the `db` service references directly rather
than building) into one portable tar, and reproduce a genuinely offline
start from that tar alone on a prepared laptop.

Why this exists: infra/README.md already documents that the FIRST
`docker compose up --build` needs internet (to pull base images and
install pip/npm packages). This script closes that gap for a real offline
deployment -- build and export once online, transfer the one tar file (and
this repo checkout) to the target machine, then start with no network at
all.

No-pull contract (P10 fix): `--no-build` alone only stops Compose from
*building*; `verify` below makes the stronger claim explicit by also
passing `--pull never`, so Compose hard-fails immediately if any image
genuinely needed a network fetch, instead of possibly succeeding by
silently reaching the registry. `verify` also checks the tar's own
manifest.json for the exact expected image set *before* touching Docker,
so a short/corrupt export is caught with a clear message rather than an
obscure failure partway through `up`.

Usage (on a machine with internet access):
    python3 tools/offline_bundle.py export --out parakh-offline-images.tar

Usage (on the air-gapped target laptop -- Docker already installed, the
tar above and this repo checkout already transferred, see infra/README.md):
    docker load -i parakh-offline-images.tar
    docker compose -f infra/docker-compose.yml --project-name kaushalpramaan-mvp \
      up -d --no-build --pull never

Or, to prove it automatically (same thing `verify` does, plus a health
check and teardown):
    python3 tools/offline_bundle.py verify --tar parakh-offline-images.tar --teardown

Safety: `verify` defaults to a project name distinct from the real
deployment's ("kaushalpramaan-mvp", infra/docker-compose.yml's `name:`)
and unconditionally REFUSES to run against that exact name at all --
`verify`'s `docker load` would overwrite that project's image tags, and
`--teardown` runs `docker compose down -v`, which deletes Compose-managed
volumes (a real deployment's actual database and evidence). `export`
intentionally still defaults to the real project name (so the tar it
produces matches what you'd actually deploy); `verify` never does.

This script only builds/saves/loads images; it never touches .env,
evidence, or the dbdata/evidence named volumes OF A DIFFERENTLY-NAMED
project. Never pass `verify` the real deployment's own project name.
"""
import argparse
import json
import subprocess
import sys
import tarfile
import time

BUILT_SERVICES = ["api", "worker", "dashboard", "migrate"]
# The `db` service in infra/docker-compose.yml references this image
# directly (no Dockerfile/build step), so it is never covered by
# `docker compose build` and must be pulled and saved explicitly.
DIRECTLY_PULLED_IMAGES = ["postgres:16-alpine"]
HEALTHCHECKED_SERVICES = ["api", "dashboard"]

# infra/docker-compose.yml's own `name:` directive -- the project name a
# REAL local/demo deployment of this stack actually runs under. `verify`
# loads images, brings up containers and (with --teardown) runs
# `docker compose down -v` -- which deletes Compose-managed volumes. If
# `verify` were ever allowed to default to or accept this exact name, a
# plain `python3 tools/offline_bundle.py verify --tar X --teardown` run
# against a machine that happens to have the real deployment up under its
# default name would silently recreate its containers from the tar and
# then DELETE its `dbdata`/`evidence` volumes -- a real database and real
# evidence, gone, with no confirmation prompt. verify_bundle() refuses
# this name outright, unconditionally, before touching Docker at all;
# there is no flag to override it, because there is no legitimate reason
# for a disposable proof-of-offline-start to share a name with a real
# deployment in the first place -- see verify's own --project default below.
REAL_DEPLOYMENT_PROJECT_NAME = "kaushalpramaan-mvp"


class OfflineBundleError(Exception):
    """Any failure in this script that has a clear, actionable cause --
    caught once at the top of main() and reported as a one-line message,
    never as a raw traceback."""


def expected_image_tags(project: str) -> list[str]:
    return [f"{project}-{svc}" for svc in BUILT_SERVICES] + list(DIRECTLY_PULLED_IMAGES)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    try:
        return subprocess.run(cmd, check=True, **kwargs)
    except FileNotFoundError as e:
        raise OfflineBundleError(f"'{cmd[0]}' is not installed or not on PATH: {e}") from e
    except subprocess.CalledProcessError as e:
        raise OfflineBundleError(f"command failed (exit {e.returncode}): {' '.join(cmd)}") from e


def export_bundle(project: str, out: str, compose_file: str) -> None:
    run(["docker", "compose", "-p", project, "-f", compose_file, "build"])
    run(["docker", "pull", *DIRECTLY_PULLED_IMAGES])
    image_tags = expected_image_tags(project)
    run(["docker", "save", "-o", out, *image_tags])
    actual_tags = read_tar_image_tags(out)
    missing = set(image_tags) - actual_tags
    if missing:
        raise OfflineBundleError(
            f"export produced {out} but it is missing: {', '.join(sorted(missing))} -- "
            "do not transfer this tar, re-run export"
        )
    print(f"\nWrote {out} containing: {', '.join(image_tags)}")
    print("\nOn the offline target laptop (Docker already installed):")
    print(f"  docker load -i {out}")
    print(f"  docker compose -p {project} -f {compose_file} up -d --no-build --pull never")
    print("\n--no-build makes Compose refuse to build anything; --pull never makes it")
    print("refuse to fetch anything either, hard-failing instead of silently reaching")
    print("the network -- the real proof the start did not fall back to a network pull.")
    print(f"\nOr verify this automatically (uses a separate, disposable --project by default -- never")
    print(f"the real deployment's project name above, see verify_bundle()'s own hard check):")
    print(f"  python3 tools/offline_bundle.py verify --tar {out} --teardown")


def _normalize_tag(tag: str) -> str:
    """`docker save` always writes an explicit tag into manifest.json
    (e.g. "kaushalpramaan-mvp-api:latest"), but expected_image_tags() above
    deliberately omits the implicit ":latest" (matching how these tags are
    referenced everywhere else in this script/infra/docker-compose.yml) --
    normalize both to the same form so the comparison in verify_bundle()
    isn't a false mismatch. A real explicit tag like "postgres:16-alpine"
    is left untouched."""
    return tag[: -len(":latest")] if tag.endswith(":latest") else tag


def read_tar_image_tags(tar_path: str) -> set[str]:
    """Every tag docker save actually wrote into the tar's own manifest,
    read directly -- no Docker daemon needed for this check, so a short or
    corrupt export is caught before anything touches `docker load`."""
    try:
        with tarfile.open(tar_path) as tf:
            try:
                member = tf.extractfile("manifest.json")
            except KeyError as e:
                raise OfflineBundleError(f"{tar_path} has no manifest.json -- not a valid `docker save` tar") from e
            if member is None:
                raise OfflineBundleError(f"{tar_path} has no manifest.json -- not a valid `docker save` tar")
            manifest = json.load(member)
    except FileNotFoundError as e:
        raise OfflineBundleError(f"tar not found: {tar_path}") from e
    except tarfile.TarError as e:
        raise OfflineBundleError(f"{tar_path} is not a valid tar: {e}") from e
    except json.JSONDecodeError as e:
        raise OfflineBundleError(f"{tar_path}'s manifest.json is not valid JSON: {e}") from e
    return {_normalize_tag(tag) for entry in manifest for tag in (entry.get("RepoTags") or [])}


def _service_health(project: str, service: str) -> str:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Health.Status}}", f"{project}-{service}-1"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "missing"


def wait_for_healthy(project: str, services: list[str], timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    statuses: dict[str, str] = {}
    while time.monotonic() < deadline:
        statuses = {svc: _service_health(project, svc) for svc in services}
        if all(status == "healthy" for status in statuses.values()):
            print(f"healthy: {statuses}")
            return
        time.sleep(2)
    raise OfflineBundleError(
        f"services did not become healthy within {timeout_seconds}s: {statuses} -- "
        f"check `docker compose -p {project} logs`"
    )


def verify_bundle(project: str, tar_path: str, compose_file: str, timeout_seconds: int, teardown: bool) -> None:
    if project == REAL_DEPLOYMENT_PROJECT_NAME:
        raise OfflineBundleError(
            f"refusing to verify against project name '{REAL_DEPLOYMENT_PROJECT_NAME}' -- that is the "
            "real deployment's own project name (infra/docker-compose.yml's `name:`), and verify's "
            "`docker load` (overwrites that project's image tags) and --teardown (`docker compose down "
            "-v`, deletes its dbdata/evidence volumes) would silently damage or destroy a real running "
            "deployment under that name. Pass a different, disposable --project (the default already is "
            "one) -- verify is a throwaway proof, never meant to run against the real deployment's name."
        )
    expected = set(expected_image_tags(project))
    actual = read_tar_image_tags(tar_path)
    missing = expected - actual
    if missing:
        raise OfflineBundleError(
            f"{tar_path} is missing required images: {', '.join(sorted(missing))} -- re-export before verifying"
        )
    print(f"tar contains all {len(expected)} required images")

    try:
        run(["docker", "load", "-i", tar_path])
        # --no-build: refuse to build anything, use only the loaded images.
        # --pull never: refuse to fetch anything either, for every service
        # including `db` (image: postgres:16-alpine, never built) -- this
        # is the strict proof neither flag alone fully gives on its own.
        run(["docker", "compose", "-p", project, "-f", compose_file, "up", "-d", "--no-build", "--pull", "never"])
        wait_for_healthy(project, HEALTHCHECKED_SERVICES, timeout_seconds)
        print("\nOFFLINE VERIFY PASSED: stack started from the loaded tar alone, "
              "with Docker refusing to build or pull anything, and became healthy.")
    finally:
        if teardown:
            subprocess.run(["docker", "compose", "-p", project, "-f", compose_file, "down", "-v"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and bundle every image the PARAKH stack needs, for a genuinely offline redeploy."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser("export", help="build (online) and save every required image into one tar")
    export_p.add_argument("--project", default="kaushalpramaan-mvp", help="docker compose project name")
    export_p.add_argument("--compose-file", default="infra/docker-compose.yml")
    export_p.add_argument("--out", default="parakh-offline-images.tar")

    verify_p = sub.add_parser(
        "verify",
        help="load the tar and start the stack with --no-build --pull never, proving no network pull occurs",
    )
    # Deliberately NOT "kaushalpramaan-mvp" (the real deployment's project
    # name) -- verify is a throwaway proof-of-offline-start that loads
    # images and (with --teardown) deletes volumes; sharing the real
    # deployment's name would risk damaging or destroying it. See
    # REAL_DEPLOYMENT_PROJECT_NAME and verify_bundle()'s hard check above.
    verify_p.add_argument("--project", default="kaushalpramaan-mvp-offline-verify")
    verify_p.add_argument("--compose-file", default="infra/docker-compose.yml")
    verify_p.add_argument("--tar", required=True)
    verify_p.add_argument("--timeout", type=int, default=120, help="seconds to wait for services to report healthy")
    verify_p.add_argument("--teardown", action="store_true", help="docker compose down -v when done (success or failure)")

    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            export_bundle(args.project, args.out, args.compose_file)
        elif args.command == "verify":
            verify_bundle(args.project, args.tar, args.compose_file, args.timeout, args.teardown)
    except OfflineBundleError as e:
        print(f"offline_bundle.py: FAILED -- {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

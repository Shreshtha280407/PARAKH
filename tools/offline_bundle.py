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

Usage (on a machine with internet access):
    python3 tools/offline_bundle.py export --out parakh-offline-images.tar

Usage (on the air-gapped target laptop -- Docker already installed, the
tar above and this repo checkout already transferred, see infra/README.md):
    docker load -i parakh-offline-images.tar
    docker compose -f infra/docker-compose.yml --project-name kaushalpramaan-mvp up -d --no-build

`--no-build` is the important part: it makes Compose refuse to build
anything and use only the exact images `docker load` just restored, which
is what proves the start didn't quietly fall back to a network pull.

This script only builds and saves images; it never touches .env, evidence,
or the dbdata/evidence named volumes.
"""
import argparse
import subprocess

BUILT_SERVICES = ["api", "worker", "dashboard", "migrate"]
# The `db` service in infra/docker-compose.yml references this image
# directly (no Dockerfile/build step), so it is never covered by
# `docker compose build` and must be pulled and saved explicitly.
DIRECTLY_PULLED_IMAGES = ["postgres:16-alpine"]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def export_bundle(project: str, out: str, compose_file: str) -> None:
    run(["docker", "compose", "-p", project, "-f", compose_file, "build"])
    run(["docker", "pull", *DIRECTLY_PULLED_IMAGES])
    image_tags = [f"{project}-{svc}" for svc in BUILT_SERVICES] + DIRECTLY_PULLED_IMAGES
    run(["docker", "save", "-o", out, *image_tags])
    print(f"\nWrote {out} containing: {', '.join(image_tags)}")
    print("\nOn the offline target laptop (Docker already installed):")
    print(f"  docker load -i {out}")
    print(f"  docker compose -p {project} -f {compose_file} up -d --no-build")
    print("\n--no-build makes Compose refuse to build anything and use only the")
    print("images docker load just restored -- the real proof the start did not")
    print("fall back to a network pull or an online rebuild.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and bundle every image the PARAKH stack needs, for a genuinely offline redeploy."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser("export", help="build (online) and save every required image into one tar")
    export_p.add_argument("--project", default="kaushalpramaan-mvp", help="docker compose project name")
    export_p.add_argument("--compose-file", default="infra/docker-compose.yml")
    export_p.add_argument("--out", default="parakh-offline-images.tar")

    args = parser.parse_args(argv)
    if args.command == "export":
        export_bundle(args.project, args.out, args.compose_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

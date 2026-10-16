# infra/

`docker-compose.yml` runs the full demo stack: PostgreSQL, the API, the
durable worker, and the React assessor dashboard — all from one command.

## Prerequisites

- Docker + Docker Compose v2
- A `.env` at the repo root: `cp .env.example .env` (fill in real values —
  see `.env.example` for what each one does; `JWT_SECRET` and
  `DEV_ASSESSOR_PASSWORD` in particular should not be left at placeholder
  values outside a throwaway local demo)

## Clean start (fresh clone → healthy stack)

```
cp .env.example .env            # edit if you want real values instead of placeholders
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api python -m app.seed
```

`up --build` builds all 4 images (db is pulled, not built), runs
`migrate` (Alembic, one-shot, `api`/`worker` wait for it to exit 0 before
they start), then brings up `api`, `worker`, `dashboard`. On a normal
machine with Docker already installed and a working internet connection
for the initial image/package pulls, this completes in a few minutes —
comfortably under the 10-minute budget.

Check it's healthy:

```
docker compose -f infra/docker-compose.yml ps        # api, db, dashboard should show "healthy"
curl http://localhost:8000/health                     # {"status":"ok","database":"ok","storage":"ok"}
open http://localhost:5173                            # or curl -I it; log in with the seeded assessor
```

Seeded assessor login: the email/password you put in `.env`'s
`DEV_ASSESSOR_EMAIL` / `DEV_ASSESSOR_PASSWORD` (seeding skips setting a
password, and that account simply can't log in, if you leave
`DEV_ASSESSOR_PASSWORD` unset).

`python -m app.seed` also creates three demo workers/assessments -- fine
for a local demo, wrong for a real deployment. For a real environment
where the only thing needed is one genuine assessor login with no demo
data at all, provision it instead with
`docker compose -f infra/docker-compose.yml exec api python -m app.provision_assessor
--email you@yourorg.example --display-name "Your Name"` (prompts for a
password interactively; see `server/app/provision_assessor.py`). You still
need `python -m app.pack_import` (or the seed step above, which calls it)
to import the qualification pack itself -- that's real configuration data,
not demo data.

## Shutdown

```
docker compose -f infra/docker-compose.yml down
```

Containers and the network are removed; the `dbdata` and `evidence` named
volumes are kept (your seeded data survives a restart).

## Full reset (wipe the database and evidence volume too)

```
docker compose -f infra/docker-compose.yml down -v
```

Then re-run the clean-start steps above.

## Running the backend test suite

`server/tests/` is not copied into the `api`/`worker` images (see
`server/.dockerignore`) -- it's not part of the deployed app, and running it
against this stack's `db` would be mixing test data with your seeded demo
data. Run it locally instead, against its own ephemeral database
(in-memory SQLite by default, or a real Postgres via `TEST_DATABASE_URL` --
see `server/README.md`):

```
cd server && source .venv/bin/activate && python -m pytest tests
```

## A note on "offline"

This Docker stack itself is not meant to be fetched or run without
internet — `docker compose up --build` needs to pull `postgres:16-alpine`,
`python:3.12-slim`, `node:22-alpine`, `nginx:alpine` and install pip/npm
packages the first time, same as any other Docker Compose project. **Do
not read "offline" as "this stack works with no internet connection ever."**

That said, P10 closes this for a genuine offline *deployment*: build and
export the images once on a machine with internet, then start them on a
network-isolated laptop from that export alone, no pulls or builds at all.
See `tools/offline_bundle.py` and `docs/deployment/README.md`'s "Offline
deployment" section.

What "offline" actually means in this product (master plan): the worker's
**Android app** captures declarations and evidence while genuinely
offline (airplane mode, no connectivity at the job site), queues it
locally, and syncs to this server once the device reaches a network where
the server is reachable — whether that's this local Docker stack on a
laptop at a demo/training site, or a real deployed instance later. The
server itself is always a normal networked service; it is the *worker's
capture step* that is offline-first, not the backend's deployment.

## Reaching this stack from a physical Android device (P6)

The `api` service binds `0.0.0.0:8000` (see `docker-compose.yml`'s `ports:`),
so it is reachable from another device on the same LAN/Wi-Fi/hotspot at
`http://<this-laptop's-LAN-IP>:8000` — not just `localhost`. Find the
laptop's real LAN IP (`ip addr` / `ifconfig` on Linux/macOS,
`ipconfig` on Windows) and confirm it from the phone first
(`adb shell curl -s http://<laptop-ip>:8000/health` once ADB is connected,
or just open that URL in the phone's browser). A **debug** Android build
only (see `docs/gates/P6.md`) can then be pointed at that address via the
in-app `P6_TEST_ONLY sync server URL` field on the sealed-assessment
screen — this works over plain HTTP because the debug build's network
security config permits cleartext specifically for this purpose; a release
build cannot be pointed at a non-HTTPS address at all. If the laptop's
firewall blocks inbound connections on port 8000, allow it for the
duration of the test (e.g. `sudo ufw allow 8000` on Ubuntu), or use a
firewall-less hotspot/router instead.

## Full command reference

```
docker compose -f infra/docker-compose.yml up -d --build   # build + start everything
docker compose -f infra/docker-compose.yml ps               # service status / health
docker compose -f infra/docker-compose.yml logs -f api       # tail one service's logs
docker compose -f infra/docker-compose.yml exec api python -m app.seed   # seed demo data
docker compose -f infra/docker-compose.yml exec api alembic upgrade head # re-run migrations manually
docker compose -f infra/docker-compose.yml down              # stop, keep volumes
docker compose -f infra/docker-compose.yml down -v           # stop, wipe volumes (full reset)
```

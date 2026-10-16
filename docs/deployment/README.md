# Deployment guide (P10.2 / P10.5)

This covers three scenarios the same codebase supports: local development,
offline/LAN deployment (e.g. a training site with no internet), and a later
hosted HTTPS deployment. It complements `infra/README.md` (local dev
quick-start) rather than replacing it.

Nothing here claims a remote host has actually been provisioned. This
document makes the hosted path *configurable and tested locally in a
production-like way*; the owner still chooses and pays for an actual host.

## 1. Prerequisites

- Docker Engine + Docker Compose v2 (`docker compose version`), already
  installed on whichever machine runs the stack. This project does not
  install Docker itself.
- For Android: the release endpoint is set at build time (see §4) -- no
  server-side Android prerequisite beyond reachability.

## 2. Local development

See `infra/README.md`. Short version:

```sh
cp .env.example .env   # fill in real values
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api python -m app.pack_import
docker compose -f infra/docker-compose.yml exec api python -m app.provision_assessor \
  --email you@yourorg.example --display-name "Your Name"   # real account, no demo data
# -- or, for a throwaway local demo with sample workers/assessments instead:
docker compose -f infra/docker-compose.yml exec api python -m app.seed
```

Host ports are configurable (useful when 8000/5173 are already taken, or
when running more than one stack on the same machine for testing):
`API_HOST_PORT` / `DASHBOARD_HOST_PORT` env vars, default 8000/5173.

## 3. Offline / LAN deployment

Target: a laptop at a training site, no internet access, reachable by
Android devices over the same Wi-Fi/hotspot.

### 3.1 Build and export images (on a machine WITH internet)

```sh
python3 tools/offline_bundle.py export --project kaushalpramaan-mvp --out parakh-offline-images.tar
```

This runs `docker compose build` (pulls base images + installs
pip/npm packages, same as any Docker build) and then `docker save`s the
four built images plus `postgres:16-alpine` (the one image the `db`
service references directly, not via a Dockerfile) into one tar.

### 3.2 Transfer

Copy to the offline laptop: this repository checkout (for
`infra/docker-compose.yml`, `.env`, and the pinned qualification pack under
`packs/`), the exported tar, and nothing else. Do not transfer `.git`
history, `server/tests/`, or any real private evidence.

### 3.3 Start with no network at all

```sh
docker load -i parakh-offline-images.tar
docker compose -f infra/docker-compose.yml --project-name kaushalpramaan-mvp up -d --no-build
```

`--no-build` is the important flag: Compose will refuse to build anything
and uses only the images `docker load` just restored. If an image is
missing, this fails loudly instead of silently trying to reach the
network.

**This was verified for real during P10**: the four built images (and
`postgres:16-alpine`, confirmed present in the exported tar's
`manifest.json`) were deleted from the local Docker image store, reloaded
from the exported tar alone, and started with `--no-build` -- the stack
came up healthy (`/health` → `{"status":"ok","database":"ok","storage":"ok"}`,
dashboard → HTTP 200) with no image anywhere that could have come from a
network pull during that `up`. (`postgres:16-alpine` itself was not
force-deleted in that run because other, unrelated local containers on the
test machine were using it -- the tar's manifest was inspected directly
instead to confirm it was genuinely bundled. On a real target laptop with
nothing else running, the full delete-then-load proof applies to all five
images.)

### 3.4 Reach it from an Android device on the same LAN

See `infra/README.md`'s "Reaching this stack from a physical Android
device" section -- unchanged by P10. A release Android build cannot use
plain HTTP at all (network security config forbids cleartext
unconditionally); for a LAN-only offline deployment either put a trusted
HTTPS reverse proxy with a real or locally-trusted certificate in front of
the API, or use a debug build for that deployment (its network security
config explicitly permits cleartext, and its sync endpoint is
runtime-configurable in-app -- see §4).

## 4. Android endpoint configuration

`apps/android/app/src/{debug,release}/.../SyncEndpointConfigFactory.kt`
already implements this correctly; no code change was needed, only this
documentation.

- **Release**: the base URL is a build-time constant
  (`BuildConfig.P6_RELEASE_SYNC_BASE_URL`), set via a Gradle property, never
  hardcoded in source and never overridable at runtime:

  ```sh
  cd apps/android
  ./gradlew :app:assembleRelease -PreleaseSyncBaseUrl=https://api.yourorg.example \
    -PRELEASE_STORE_FILE=/secure/path/release.keystore \
    -PRELEASE_STORE_PASSWORD=*** -PRELEASE_KEY_ALIAS=*** -PRELEASE_KEY_PASSWORD=***
  ```

  Omitting `-PreleaseSyncBaseUrl` falls back to the placeholder
  `https://api.kaushalpramaan.example` (a non-existent host, by design --
  distinguishable from a real target, never silently `localhost`).
  Omitting the four `RELEASE_*` signing properties (or the matching
  environment variables) falls back to the debug keystore with a logged
  warning, so the build still succeeds but is clearly not really
  release-signed -- verified during P10 (`app-release.apk` built, signed
  with the fallback, `apksigner verify` confirms the signer, installed and
  launched cleanly on a real OnePlus 13R with no crash).
  `android:usesCleartextTraffic="false"` is enforced for release
  unconditionally (own Gradle verification task,
  `verifyReleaseForbidsCleartextTraffic`) -- a release build architecturally
  cannot be pointed at a plain-HTTP endpoint.
- **Debug**: defaults to `http://10.0.2.2:8000` (emulator-to-host alias),
  runtime-overridable in-app (a plain SharedPreferences field, not a
  secret) for pointing at a real LAN IP during physical testing. Proven
  absent from release's compiled output by
  `verifyP6SyncEndpointOverrideAbsentFromRelease`.

## 5. Dashboard API configuration

Two layers, both real (`apps/dashboard/src/api.ts`, `Dockerfile`,
`docker/write-runtime-config.sh`):

1. **Build-time default** (`VITE_API_BASE_URL`, baked in by Vite): fine for
   a single-environment build, but ties one built image to one backend
   origin forever.
2. **Runtime override** (P10, new): the dashboard's nginx container
   regenerates `/config.json` from `$DASHBOARD_RUNTIME_API_BASE_URL` on
   every container start, and the app fetches it before its first API
   call. This lets the *same already-built* dashboard image be redeployed
   against a different backend (e.g. once a real hosted domain is chosen)
   by changing one environment variable and restarting the container --
   no rebuild. Verified during P10: built once, confirmed `{}` (build-time
   default) with no override, then `{"apiBaseUrl":"https://..."}` after
   setting the env var and recreating only the container (not rebuilding),
   then exercised end-to-end by a real browser.

```sh
# at deploy time, once the real hosted API origin is known:
DASHBOARD_RUNTIME_API_BASE_URL=https://api.yourorg.example \
  docker compose -f infra/docker-compose.yml up -d dashboard
```

Protected media (`<img>`/`<video>` tags), the public verify page, and
report downloads all read the same `BASE_URL` -- no separate configuration
needed for them.

## 6. Hosted HTTPS deployment configuration

Not performed in P10 (no remote host chosen or paid for). Everything below
is implemented and testable locally in a production-like way; a later
hosted deployment plugs real values into the same variables.

| Concern | Variable / mechanism | Notes |
|---|---|---|
| Environment | `APP_ENV=production` (or `staging`) | Gates every fail-fast check below |
| HTTPS | reverse proxy in front of `api`/`dashboard` (not included -- bring your own, e.g. Caddy/nginx/Traefik with a real cert) | The API itself serves plain HTTP; TLS termination is an infra decision, same as `docs/worker_capability_tokens.md` already discloses |
| CORS | `CORS_ALLOW_ORIGINS=https://dashboard.yourorg.example` | Rejects `*` and (outside dev) any `localhost` origin at startup -- fail-fast, not silent |
| Cookies | `secure`/`samesite=lax` auto-derived from `APP_ENV`; optional `COOKIE_DOMAIN` (P10, new) | Only set `COOKIE_DOMAIN` if dashboard+API are on different subdomains of one parent domain |
| CSRF | double-submit cookie, always on for cookie-authenticated mutations | No configuration needed |
| Login throttle | in-memory, 5 failed attempts / 15 min per email (P10, new) | Per-process -- a multi-replica deployment needs a shared store (e.g. Redis) for this to hold across replicas; not needed for a single-instance deployment |
| Database | `DATABASE_URL` → a real, persistent, backed-up PostgreSQL instance | Do not point this at an ephemeral/free-tier filesystem-backed instance |
| Evidence storage | `EVIDENCE_DIR` → a persistent volume/mount, backed up | Same durability requirement as the database |
| Report signing key | `REPORT_SIGNING_PRIVATE_KEY` (+ `_KEY_ID`, `_KEY_HISTORY` on rotation) | Fails fast if unset, in every `APP_ENV` -- never regenerates itself. Store it as a real secret (vault/secret manager), never in `.env` committed anywhere |
| Public verify origin | `REPORT_VERIFY_BASE_URL` → the real deployed dashboard origin | What a signed PDF's QR code actually points at |
| Secrets | `JWT_SECRET`, `REPORT_SIGNING_PRIVATE_KEY`, DB password | All fail-fast if unset outside development; none has a usable hardcoded default |
| Migrations | `migrate` one-shot service, `api`/`worker` wait for it (`service_completed_successfully`) | Unchanged by P10 -- additive-only migrations, verified against a populated prior schema in existing tests |
| Worker process | `worker` service, `restart: unless-stopped` (P10, new) | Recovers from a crash automatically |
| Backup/restore | `pg_dump`/`pg_restore` for the database; a filesystem/object-storage backup tool for the `evidence` volume | Not implemented by this repo -- standard PostgreSQL/filesystem backup practice applies; test a restore before relying on it |

### 6.1 Clean-install provisioning

A fresh environment must not contain synthetic workers/assessments. Use
`python -m app.pack_import` (real qualification-pack data) and
`python -m app.provision_assessor` (one real account, interactive password
prompt, no demo side effects) -- never `python -m app.seed` outside a local
demo. Verified during P10 end-to-end on a disposable stack: fresh database
→ pack import → `provision_assessor` → real login → empty queue (no
synthetic records).

## 7. Health checks

```sh
curl http://<host>:<api-port>/health        # {"status":"ok","database":"ok","storage":"ok"}
curl -I http://<host>:<dashboard-port>/     # 200
docker compose -f infra/docker-compose.yml ps   # all services "healthy"
```

## 8. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `api`/`worker` won't start, log shows a pydantic `ValidationError` about `JWT_SECRET`/`REPORT_SIGNING_PRIVATE_KEY`/`CORS_ALLOW_ORIGINS` | A required secret/config value is unset or still a placeholder outside `development` -- this is a deliberate fail-fast, not a bug |
| Dashboard loads but every request fails/CORS error in the browser console | `CORS_ALLOW_ORIGINS` doesn't match the dashboard's actual origin, or the dashboard's `BASE_URL`/runtime config points at the wrong API origin |
| Login succeeds (200) but the next authenticated call 401s | The dashboard and API are on different hostnames that the browser treats as different sites (e.g. `127.0.0.1` vs `localhost`) -- `SameSite=Lax` session cookies are not sent cross-site on `fetch`. Use the same hostname for both, or set `COOKIE_DOMAIN` if they're true subdomains of one parent domain |
| `docker compose up --no-build` fails with "no such image" | The offline bundle wasn't `docker load`ed first, or the project name used at `up` doesn't match the one used at `export`/`load` (image tags are `<project>-<service>`) |
| A release Android build won't connect over plain HTTP | Expected and by design -- release forbids cleartext unconditionally. Use HTTPS, or a debug build for LAN-only testing |

## 9. What P10 did and did not do here

Implemented and verified locally: offline image export/reload/start
cycle, dashboard runtime API reconfiguration without rebuild, Android
release signing + endpoint configuration, clean-install provisioning
without demo data, `restart: unless-stopped` recovery policies, configurable
host ports, `COOKIE_DOMAIN` support, documented hosted-config variables.

Not done (owner's remaining work, by design -- see `docs/gates/P10.md`):
choosing/paying for an actual hosting provider, provisioning real DNS/TLS,
and performing the actual hosted deployment.

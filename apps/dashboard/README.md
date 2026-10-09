# apps/dashboard — assessor web dashboard

React + TypeScript + Vite. Intentionally basic/functional, not polished —
see `docs/gates/P2_1.md`. Assessor/admin only; the worker mobile app has no
web counterpart here (see `docs/worker_capability_tokens.md`).

## Local dev

```
npm install
cp .env.example .env.local       # set VITE_API_BASE_URL if the API isn't on localhost:8000
npm run dev                      # http://localhost:5173
```

## Build / typecheck

```
npm run build    # tsc -b && vite build -- fails on type errors
```

## Docker

Built as part of `infra/docker-compose.yml` (`apps/dashboard/Dockerfile`,
multi-stage: `npm run build` in a Node image, served by `nginx:alpine`).
`VITE_API_BASE_URL` is baked in at **build** time (Vite inlines
`import.meta.env.*`), via the `DASHBOARD_API_BASE_URL` build arg in
`infra/docker-compose.yml` — a runtime env var on the container would be
too late to affect an already-built bundle.

## What it does

- Login (assessor email/password → JWT, stored in `sessionStorage`,
  cleared on logout — see `src/auth.ts` for why that's "good enough for a
  demo" and not more).
- Protected queue (`GET /queue`) with loading/empty/error states.
- Assessment detail: worker summary, QP, the fixed five tasks with
  per-task budget/evidence-used, each evidence item's server-verified
  SHA-256, and an on-demand rubric viewer. No scoring UI — rubric is
  read-only reference (see `docs/evidence_status_model.md`).

No worker-facing functionality lives here, and no screen shows
hard-coded/fake data — every page fetches from the real API.

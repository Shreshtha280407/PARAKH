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

- Login (assessor email/password → HttpOnly cookie session + CSRF
  double-submit token, cleared on logout — see `docs/gates/P2_2.md`
  section 8; no token is ever held in JS-readable storage).
- Protected queue (`GET /queue`) with loading/empty/error states.
- Assessment detail (`AssessmentDetailPage.tsx`) — the full review
  workspace:
  - Worker summary, QP, status.
  - **Declaration & QP match** (P6): the synced match-result/coverage/gap-
    task summary — a bounded snapshot, not the worker's full declaration
    (see `docs/gates/P6.md`'s stated limitation).
  - **Sync & package integrity** (P6): per-revision manifest/item
    verification state (`GET /assessments/{id}/sync-status`).
  - **Evidence by task** (P6): real per-task tabs, a protected
    gallery/player (playable `<video>`/`<img>` against the authenticated
    evidence-content endpoint, with a safe fallback if the media or its
    thumbnail job failed) and real extracted width/height/duration.
  - Rubric (read-only reference), PC scoring (0–3 + evidence status +
    remarks, optimistic-locked), competency profile (decision-support
    only, never a pass/fail), recommendation/decision, reassessment,
    signed-report generate/download/verify, worker-token rotate/revoke —
    all P2.2, extended in presentation by P6, not reimplemented.
  - **Audit log** (P6): the full append-only action trail
    (`GET /assessments/{id}/audit-log`), including old/new values on a
    rescore.

No worker-facing functionality lives here, and no screen shows
hard-coded/fake data — every page fetches from the real API. The dashboard
never says the system "certified" or "passed" the worker — every
recommendation is an explicit human assessor action.

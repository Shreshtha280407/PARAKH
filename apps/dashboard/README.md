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
    remarks, optimistic-locked), worker-token rotate/revoke — P2.2,
    extended in presentation by P6, not reimplemented.
  - **Competency profile** (P7): the pinned-pack-data *computed* outcome
    (`server/app/outcome.py`) per NOS — meets-threshold, critical-PC
    violation, insufficient-evidence flags — always labelled
    decision-support only, never a pass/fail the system itself declares.
  - **Targeted reassessment** (P7): a dialog to reopen specific task(s)
    with a mandatory reason + capture instructions; the existing
    whole-assessment "Needs reassessment" restart (P2.2) stays available
    alongside it for when a full restart is the right call.
  - **Sign off** (P7): password re-entered and verified server-side
    against the authenticated assessor (never a frontend-only check);
    `override_reason` becomes a required field the moment the chosen
    final recommendation differs from the computed one (server-enforced
    422, not just a UI nicety); produces the one immutable, Ed25519-signed
    PDF for this assessment — never regenerated on re-download.
  - **Revision history** (P7): v1/v2/… table plus the reassessment-request
    log, so a resubmission's provenance (which tasks were reopened, by
    whom, why) stays visible alongside the current evidence.
  - **Audit log** (P6): the full append-only action trail
    (`GET /assessments/{id}/audit-log`), including old/new values on a
    rescore.
- **Public report verification** (P7, `#/verify/:reportId`,
  `VerifyReportPage.tsx`): rendered *before* the login gate in `App.tsx` —
  the exact page a signed PDF's own QR code points at, for an arbitrary
  third party who scanned it, not a logged-in assessor. No cookie, no
  credentials sent.

No worker-facing functionality lives here, and no screen shows
hard-coded/fake data — every page fetches from the real API. The dashboard
never says the system "certified" or "passed" the worker — every
recommendation is an explicit human assessor action, and every signed
report carries the words "Assessor recommendation — not an official
certificate."

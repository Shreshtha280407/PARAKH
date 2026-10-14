# contracts/

`openapi.json` is generated from the FastAPI app, never hand-maintained --
see `tools/export_openapi.py`. It covers the full current backend surface:
auth, assessments, resumable+manifest-verified uploads (P6), queue, admin,
scoring/decisions/reports (P2.2), worker self-registration and pack lookup
(P6), sync status and the audit log (P6), computed-outcome/task-specific
reassessment/worker-updates/password-confirmed sign-off/public report
verification (P7), and every error schema FastAPI derives from the
endpoints' declared response models and `HTTPException` usage.

Regenerate after any backend route/schema change:

```
python tools/export_openapi.py
```

CI fails if the committed file doesn't match what the current code would
generate (`python tools/export_openapi.py --check`, see
`.github/workflows/ci.yml`) -- the contract can never silently drift from
the real API.

`mapping_vectors.json` + `flags.schema.json` (AI team <-> app contract) are
still P3+ scope -- no AI/CV inference exists yet to have a contract for.

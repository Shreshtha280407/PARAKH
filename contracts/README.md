# contracts/

`openapi.json` is generated from the FastAPI app, never hand-maintained --
see `tools/export_openapi.py`. It covers the full P2.1 surface: auth,
assessments, resumable uploads, queue, admin, and every error schema FastAPI
derives from the endpoints' declared response models and `HTTPException`
usage.

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

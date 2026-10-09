# infra/

`docker-compose.yml` for local development/demo infrastructure. Eventually
the full demo laptop setup (api + worker + db + dashboard, local Wi-Fi
router/hotspot, no internet) — for now, P2 only needs `db` (PostgreSQL 16).

```
docker compose -f infra/docker-compose.yml up -d
```

Then point the API at it: `PARAKH_DATABASE_URL=postgresql+psycopg://parakh:parakh@localhost:5432/parakh`
(this is already the default in `server/app/config.py`).

The `api`, `worker`, and `dashboard` services are added once those apps
exist (P2 backend is run directly via `uvicorn` in dev for now; the
dashboard is P6).

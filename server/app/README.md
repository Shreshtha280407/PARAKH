# server/app/

FastAPI backend (auth, assessments, resumable+manifest-verified uploads,
review/scoring, reports, audit, sync status). `app/worker.py` is the
background job runner (`python -m app.worker`), run as its own process/
container (see `infra/docker-compose.yml`'s `worker` service).

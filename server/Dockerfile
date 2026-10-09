# Build context is the REPO ROOT (see infra/docker-compose.yml's
# `build: {context: .., dockerfile: server/Dockerfile}`), not server/ --
# pack_import.py needs tools/pack_validate.py, tools/audit_qp_traceability.py
# and packs/ae-con-q0602/ (P1 artifacts, outside server/) to re-validate a
# pack before importing it.
FROM python:3.12-slim

WORKDIR /code
# Guarantees `app.*` resolves regardless of how the CMD/entrypoint is
# invoked (uvicorn, alembic, python -m app.worker, python -m app.seed all
# need it). Also tells pack_import.py/seed.py where packs/ and tools/ live
# in THIS image layout (see server/app/pack_import.py).
ENV PYTHONPATH=/code
ENV PARAKH_REPO_ROOT=/code

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/app ./app
COPY server/alembic ./alembic
COPY server/alembic.ini .
COPY tools ./tools
COPY packs ./packs

# Default command is the API; infra/docker-compose.yml overrides this for
# the migrate (one-shot `alembic upgrade head`) and worker services, which
# share this same image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

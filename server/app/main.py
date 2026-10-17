from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import admin, assessments, auth, decisions, evidence, health, packs, queue, reassessment, reports, scoring, tokens, uploads, verify, workers
from .routers import public, reviewer

app = FastAPI(title="KaushalPramaan API", version="0.6.0")


@app.exception_handler(RequestValidationError)
async def private_validation_errors(_request, error):
    # Pydantic normally reflects invalid input, including accidental secrets.
    # Return validation locations/messages without echoing phone, PIN or tokens.
    return JSONResponse(status_code=422, content={"detail": [
        {"type": item["type"], "loc": list(item["loc"]), "msg": item["msg"]}
        for item in error.errors()
    ]})

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",")],
    allow_credentials=True,  # the dashboard's session cookie (P2.2 section 7) requires this
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(assessments.router)
app.include_router(uploads.router)
app.include_router(queue.router)
app.include_router(admin.router)
app.include_router(scoring.router)
app.include_router(decisions.router)
app.include_router(reports.router)
app.include_router(evidence.router)
app.include_router(tokens.router)
app.include_router(workers.router)
app.include_router(packs.router)
app.include_router(reassessment.router)
app.include_router(verify.router)
app.include_router(public.router)
app.include_router(reviewer.router)

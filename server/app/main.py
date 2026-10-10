from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import admin, assessments, auth, decisions, evidence, health, queue, reports, scoring, tokens, uploads

app = FastAPI(title="KaushalPramaan API", version="0.3.0")

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

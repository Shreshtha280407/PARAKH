from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import admin, assessments, auth, health, queue, uploads

app = FastAPI(title="KaushalPramaan API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",")],
    allow_credentials=False,  # Bearer-token auth, no cookies -- credentials aren't needed
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(assessments.router)
app.include_router(uploads.router)
app.include_router(queue.router)
app.include_router(admin.router)

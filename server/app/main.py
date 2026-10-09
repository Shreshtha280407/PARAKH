from fastapi import FastAPI

from .routers import assessments, health, queue, uploads

app = FastAPI(title="KaushalPramaan API", version="0.2.0")

app.include_router(health.router)
app.include_router(assessments.router)
app.include_router(uploads.router)
app.include_router(queue.router)

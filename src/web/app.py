from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from src.db.init_db import init_db
from src.web.routes import (
    achievements,
    certifications,
    education,
    jobs,
    profile,
    projects,
    skills,
    tailor,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Bespoke", lifespan=lifespan)

app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(achievements.router)
app.include_router(skills.router)
app.include_router(projects.router)
app.include_router(education.router)
app.include_router(certifications.router)
app.include_router(tailor.router)


@app.get("/")
def root():
    return RedirectResponse(url="/jobs/")

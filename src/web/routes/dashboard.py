from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.session import get_session
from src.models.education import Certification, Education
from src.models.job import Job
from src.models.profile import Profile
from src.models.project import Project
from src.models.skill import Skill
from src.models.tailoring import TailoringSession
from src.tailor.scorer import compute_match_score
from src.web.deps import templates

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_session)):
    recent = db.scalars(
        select(TailoringSession)
        .order_by(TailoringSession.created_at.desc())
        .limit(5)
    ).all()

    sessions_view = []
    for s in recent:
        score = None
        if s.analysis_json:
            score = compute_match_score(s.analysis_json, db)
        sessions_view.append({"s": s, "score": score})

    counts = {
        "jobs": db.scalar(select(func.count()).select_from(Job)) or 0,
        "skills": db.scalar(select(func.count()).select_from(Skill)) or 0,
        "projects": db.scalar(select(func.count()).select_from(Project)) or 0,
        "education": db.scalar(select(func.count()).select_from(Education)) or 0,
        "certifications": db.scalar(select(func.count()).select_from(Certification)) or 0,
    }

    profile = db.get(Profile, 1)
    profile_warning = None
    if profile is None or not profile.full_name or not profile.email:
        profile_warning = (
            "Your profile is missing contact info — "
            "generated resumes won't have a header."
        )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "sessions_view": sessions_view,
            "counts": counts,
            "profile": profile,
            "profile_warning": profile_warning,
        },
    )

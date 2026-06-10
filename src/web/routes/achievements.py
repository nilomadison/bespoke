from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.session import get_session
from src.models.achievement import Achievement
from src.models.job import Job
from src.web.deps import templates

router = APIRouter(prefix="/jobs/{job_id}/achievements", tags=["achievements"])


def _get_job_or_404(job_id: int, db: Session) -> Job | HTMLResponse:
    job = db.get(Job, job_id)
    if job is None:
        return HTMLResponse(content="Job not found", status_code=404)
    return job


@router.get("/", response_class=HTMLResponse)
def list_achievements(job_id: int, request: Request, db: Session = Depends(get_session)):
    achievements = db.scalars(
        select(Achievement)
        .where(Achievement.job_id == job_id)
        .order_by(Achievement.sort_order, Achievement.id)
    ).all()
    return templates.TemplateResponse(
        request, "achievements/list.html", {"achievements": achievements, "job_id": job_id}
    )


@router.post("/", response_class=HTMLResponse)
def create_achievement(
    job_id: int,
    request: Request,
    db: Session = Depends(get_session),
    text: str = Form(...),
    metric: str = Form(""),
    impact_tags: str = Form(""),
    prominence: int = Form(3),
    sort_order: int = Form(0),
):
    tags = [t.strip() for t in impact_tags.split(",") if t.strip()]
    achievement = Achievement(
        job_id=job_id,
        text=text,
        metric=metric or None,
        impact_tags=tags,
        prominence=prominence,
        sort_order=sort_order,
    )
    db.add(achievement)
    db.commit()
    db.refresh(achievement)
    return templates.TemplateResponse(
        request, "achievements/_row.html", {"achievement": achievement, "job_id": job_id}
    )


@router.get("/{achievement_id}", response_class=HTMLResponse)
def get_achievement_row(
    job_id: int, achievement_id: int, request: Request, db: Session = Depends(get_session)
):
    achievement = db.get(Achievement, achievement_id)
    if achievement is None:
        return HTMLResponse(content="", status_code=200)
    return templates.TemplateResponse(
        request, "achievements/_row.html", {"achievement": achievement, "job_id": job_id}
    )


@router.get("/{achievement_id}/edit", response_class=HTMLResponse)
def edit_achievement_form(
    job_id: int, achievement_id: int, request: Request, db: Session = Depends(get_session)
):
    achievement = db.get(Achievement, achievement_id)
    if achievement is None:
        return HTMLResponse(content="Not found", status_code=404)
    return templates.TemplateResponse(
        request, "achievements/_row_edit.html", {"achievement": achievement, "job_id": job_id}
    )


@router.post("/{achievement_id}", response_class=HTMLResponse)
def update_achievement(
    job_id: int,
    achievement_id: int,
    request: Request,
    db: Session = Depends(get_session),
    text: str = Form(...),
    metric: str = Form(""),
    impact_tags: str = Form(""),
    prominence: int = Form(3),
    sort_order: int = Form(0),
):
    achievement = db.get(Achievement, achievement_id)
    if achievement is None:
        return HTMLResponse(content="Not found", status_code=404)
    achievement.text = text
    achievement.metric = metric or None
    achievement.impact_tags = [t.strip() for t in impact_tags.split(",") if t.strip()]
    achievement.prominence = prominence
    achievement.sort_order = sort_order
    db.commit()
    db.refresh(achievement)
    return templates.TemplateResponse(
        request, "achievements/_row.html", {"achievement": achievement, "job_id": job_id}
    )


@router.post("/{achievement_id}/delete", response_class=HTMLResponse)
def delete_achievement(job_id: int, achievement_id: int, db: Session = Depends(get_session)):
    achievement = db.get(Achievement, achievement_id)
    if achievement:
        db.delete(achievement)
        db.commit()
    return HTMLResponse(content="", status_code=200)

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.session import get_session
from src.models.job import EmploymentType, Job
from src.web.deps import templates

router = APIRouter(prefix="/jobs", tags=["jobs"])

EMPLOYMENT_TYPES = [e.value for e in EmploymentType]


@router.get("/", response_class=HTMLResponse)
def list_jobs(request: Request, db: Session = Depends(get_session)):
    jobs = db.scalars(select(Job).order_by(Job.sort_order, Job.start_date.desc())).all()
    return templates.TemplateResponse(
        request, "jobs/list.html", {"jobs": jobs, "employment_types": EMPLOYMENT_TYPES}
    )


@router.get("/new", response_class=HTMLResponse)
def new_job_form(request: Request):
    return templates.TemplateResponse(
        request, "jobs/form.html", {"job": None, "employment_types": EMPLOYMENT_TYPES}
    )


@router.post("/", response_class=HTMLResponse)
def create_job(
    request: Request,
    db: Session = Depends(get_session),
    title: str = Form(...),
    company: str = Form(...),
    location: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(""),
    employment_type: str = Form("full_time"),
    summary: str = Form(""),
    is_technical: str = Form("on"),
    sort_order: int = Form(0),
):
    job = Job(
        title=title,
        company=company,
        location=location or None,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date) if end_date else None,
        employment_type=EmploymentType(employment_type),
        summary=summary or None,
        is_technical=is_technical == "on",
        sort_order=sort_order,
    )
    db.add(job)
    db.commit()
    return RedirectResponse(url="/jobs/", status_code=303)


@router.get("/{job_id}", response_class=HTMLResponse)
def get_job(job_id: int, request: Request, db: Session = Depends(get_session)):
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .options(
            selectinload(Job.achievements),
            selectinload(Job.job_skills),
        )
    )
    if job is None:
        return HTMLResponse(content="Not found", status_code=404)
    return templates.TemplateResponse(
        request, "jobs/detail.html", {"job": job, "employment_types": EMPLOYMENT_TYPES}
    )


@router.get("/{job_id}/edit", response_class=HTMLResponse)
def edit_job_form(job_id: int, request: Request, db: Session = Depends(get_session)):
    job = db.get(Job, job_id)
    if job is None:
        return HTMLResponse(content="Not found", status_code=404)
    return templates.TemplateResponse(
        request, "jobs/form.html", {"job": job, "employment_types": EMPLOYMENT_TYPES}
    )


@router.post("/{job_id}", response_class=HTMLResponse)
def update_job(
    job_id: int,
    request: Request,
    db: Session = Depends(get_session),
    title: str = Form(...),
    company: str = Form(...),
    location: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(""),
    employment_type: str = Form("full_time"),
    summary: str = Form(""),
    is_technical: str = Form("off"),
    sort_order: int = Form(0),
):
    job = db.get(Job, job_id)
    if job is None:
        return HTMLResponse(content="Not found", status_code=404)
    job.title = title
    job.company = company
    job.location = location or None
    job.start_date = date.fromisoformat(start_date)
    job.end_date = date.fromisoformat(end_date) if end_date else None
    job.employment_type = EmploymentType(employment_type)
    job.summary = summary or None
    job.is_technical = is_technical == "on"
    job.sort_order = sort_order
    db.commit()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@router.post("/{job_id}/delete", response_class=HTMLResponse)
def delete_job(job_id: int, db: Session = Depends(get_session)):
    job = db.get(Job, job_id)
    if job:
        db.delete(job)
        db.commit()
    return RedirectResponse(url="/jobs/", status_code=303)

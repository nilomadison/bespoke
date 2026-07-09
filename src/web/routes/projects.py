from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.session import get_session
from src.models.job import Job
from src.models.project import Project
from src.web.deps import templates

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_class=HTMLResponse)
def list_projects(request: Request, db: Session = Depends(get_session)):
    projects = db.scalars(select(Project).order_by(Project.is_active.desc(), Project.name)).all()
    jobs = db.scalars(select(Job).order_by(Job.start_date.desc())).all()
    return templates.TemplateResponse(
        request, "projects/list.html", {"request": request, "projects": projects, "jobs": jobs}
    )


@router.get("/new", response_class=HTMLResponse)
def new_project_form(request: Request, db: Session = Depends(get_session)):
    jobs = db.scalars(select(Job).order_by(Job.start_date.desc())).all()
    return templates.TemplateResponse(
        request, "projects/form.html", {"request": request, "project": None, "jobs": jobs}
    )


@router.post("/", response_class=HTMLResponse)
def create_project(
    request: Request,
    db: Session = Depends(get_session),
    name: str = Form(...),
    summary: str = Form(...),
    description: str = Form(""),
    repo_url: str = Form(""),
    live_url: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    is_active: str = Form("off"),
    job_id: str = Form(""),
):
    project = Project(
        name=name,
        summary=summary,
        description=description or None,
        repo_url=repo_url or None,
        live_url=live_url or None,
        start_date=date.fromisoformat(start_date) if start_date else None,
        end_date=date.fromisoformat(end_date) if end_date else None,
        is_active=is_active == "on",
        job_id=int(job_id) if job_id else None,
    )
    db.add(project)
    db.commit()
    return RedirectResponse(url="/projects/", status_code=303)


@router.get("/{project_id}/edit", response_class=HTMLResponse)
def edit_project_form(project_id: int, request: Request, db: Session = Depends(get_session)):
    project = db.get(Project, project_id)
    if project is None:
        return HTMLResponse(content="Not found", status_code=404)
    jobs = db.scalars(select(Job).order_by(Job.start_date.desc())).all()
    return templates.TemplateResponse(
        request, "projects/form.html", {"request": request, "project": project, "jobs": jobs}
    )


@router.post("/{project_id}", response_class=HTMLResponse)
def update_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_session),
    name: str = Form(...),
    summary: str = Form(...),
    description: str = Form(""),
    repo_url: str = Form(""),
    live_url: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    is_active: str = Form("off"),
    job_id: str = Form(""),
):
    project = db.get(Project, project_id)
    if project is None:
        return HTMLResponse(content="Not found", status_code=404)
    project.name = name
    project.summary = summary
    project.description = description or None
    project.repo_url = repo_url or None
    project.live_url = live_url or None
    project.start_date = date.fromisoformat(start_date) if start_date else None
    project.end_date = date.fromisoformat(end_date) if end_date else None
    project.is_active = is_active == "on"
    project.job_id = int(job_id) if job_id else None
    db.commit()
    return RedirectResponse(url="/projects/", status_code=303)


@router.post("/{project_id}/delete", response_class=HTMLResponse)
def delete_project(project_id: int, db: Session = Depends(get_session)):
    project = db.get(Project, project_id)
    if project:
        db.delete(project)
        db.commit()
    return RedirectResponse(url="/projects/", status_code=303)

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.session import get_session
from src.models.education import Certification, Education
from src.web.deps import templates

router = APIRouter(prefix="/education", tags=["education"])


@router.get("/", response_class=HTMLResponse)
def list_education(request: Request, db: Session = Depends(get_session)):
    items = db.scalars(select(Education).order_by(Education.end_date.desc())).all()
    certs = db.scalars(select(Certification).order_by(Certification.issue_date.desc())).all()
    return templates.TemplateResponse(
        request, "education/list.html", {"request": request, "items": items, "certs": certs}
    )


@router.post("/", response_class=HTMLResponse)
def create_education(
    request: Request,
    db: Session = Depends(get_session),
    institution: str = Form(...),
    degree: str = Form(...),
    field: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
    is_in_progress: str = Form("off"),
    gpa: str = Form(""),
    honors: str = Form(""),
):
    item = Education(
        institution=institution,
        degree=degree,
        field=field,
        start_date=date.fromisoformat(start_date) if start_date else None,
        end_date=date.fromisoformat(end_date) if end_date else None,
        is_in_progress=is_in_progress == "on",
        gpa=float(gpa) if gpa else None,
        honors=honors or None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return templates.TemplateResponse(
        request, "education/_edu_row.html", {"request": request, "item": item}
    )


@router.get("/{edu_id}/view", response_class=HTMLResponse)
def get_education_row(edu_id: int, request: Request, db: Session = Depends(get_session)):
    item = db.get(Education, edu_id)
    if item is None:
        return HTMLResponse(content="", status_code=200)
    return templates.TemplateResponse(
        request, "education/_edu_row.html", {"request": request, "item": item}
    )


@router.get("/{edu_id}/edit", response_class=HTMLResponse)
def edit_education_form(edu_id: int, request: Request, db: Session = Depends(get_session)):
    item = db.get(Education, edu_id)
    if item is None:
        return HTMLResponse(content="Not found", status_code=404)
    return templates.TemplateResponse(
        request, "education/_edu_row_edit.html", {"request": request, "item": item}
    )


@router.post("/{edu_id}", response_class=HTMLResponse)
def update_education(
    edu_id: int,
    request: Request,
    db: Session = Depends(get_session),
    institution: str = Form(...),
    degree: str = Form(...),
    field: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
    is_in_progress: str = Form("off"),
    gpa: str = Form(""),
    honors: str = Form(""),
):
    item = db.get(Education, edu_id)
    if item is None:
        return HTMLResponse(content="Not found", status_code=404)
    item.institution = institution
    item.degree = degree
    item.field = field
    item.start_date = date.fromisoformat(start_date) if start_date else None
    item.end_date = date.fromisoformat(end_date) if end_date else None
    item.is_in_progress = is_in_progress == "on"
    item.gpa = float(gpa) if gpa else None
    item.honors = honors or None
    db.commit()
    db.refresh(item)
    return templates.TemplateResponse(
        request, "education/_edu_row.html", {"request": request, "item": item}
    )


@router.post("/{edu_id}/delete", response_class=HTMLResponse)
def delete_education(edu_id: int, db: Session = Depends(get_session)):
    item = db.get(Education, edu_id)
    if item:
        db.delete(item)
        db.commit()
    return HTMLResponse(content="", status_code=200)

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.session import get_session
from src.models.skill import JobSkill, Skill
from src.web.deps import templates

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/", response_class=HTMLResponse)
def list_skills(request: Request, db: Session = Depends(get_session)):
    skills = db.scalars(select(Skill).order_by(Skill.category, Skill.name)).all()
    return templates.TemplateResponse(
        request, "skills/list.html", {"request": request, "skills": skills}
    )


@router.post("/", response_class=HTMLResponse)
def create_skill(
    request: Request,
    db: Session = Depends(get_session),
    name: str = Form(...),
    category: str = Form(""),
):
    skill = Skill(name=name.strip(), category=category.strip() or None)
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return templates.TemplateResponse(
        request, "skills/_row.html", {"request": request, "skill": skill}
    )


@router.get("/{skill_id}", response_class=HTMLResponse)
def get_skill_row(skill_id: int, request: Request, db: Session = Depends(get_session)):
    skill = db.get(Skill, skill_id)
    if skill is None:
        return HTMLResponse(content="", status_code=200)
    return templates.TemplateResponse(
        request, "skills/_row.html", {"request": request, "skill": skill}
    )


@router.get("/{skill_id}/edit", response_class=HTMLResponse)
def edit_skill_form(skill_id: int, request: Request, db: Session = Depends(get_session)):
    skill = db.get(Skill, skill_id)
    if skill is None:
        return HTMLResponse(content="Not found", status_code=404)
    return templates.TemplateResponse(
        request, "skills/_row_edit.html", {"request": request, "skill": skill}
    )


@router.post("/{skill_id}", response_class=HTMLResponse)
def update_skill(
    skill_id: int,
    request: Request,
    db: Session = Depends(get_session),
    name: str = Form(...),
    category: str = Form(""),
):
    skill = db.get(Skill, skill_id)
    if skill is None:
        return HTMLResponse(content="Not found", status_code=404)
    skill.name = name.strip()
    skill.category = category.strip() or None
    db.commit()
    db.refresh(skill)
    return templates.TemplateResponse(
        request, "skills/_row.html", {"request": request, "skill": skill}
    )


@router.post("/{skill_id}/delete", response_class=HTMLResponse)
def delete_skill(skill_id: int, db: Session = Depends(get_session)):
    skill = db.get(Skill, skill_id)
    if skill:
        db.delete(skill)
        db.commit()
    return HTMLResponse(content="", status_code=200)

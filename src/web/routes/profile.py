from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.db.session import get_session
from src.models.profile import Profile
from src.web.deps import templates

router = APIRouter(tags=["profile"])


@router.get("/profile", response_class=HTMLResponse)
def get_profile(request: Request, db: Session = Depends(get_session)):
    profile = db.get(Profile, 1)
    return templates.TemplateResponse(
        request, "profile/edit.html", {"request": request, "profile": profile}
    )


@router.post("/profile", response_class=HTMLResponse)
def update_profile(
    request: Request,
    db: Session = Depends(get_session),
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    location: str = Form(""),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    portfolio_url: str = Form(""),
    baseline_summary: str = Form(""),
):
    profile = db.get(Profile, 1)
    profile.full_name = full_name
    profile.email = email
    profile.phone = phone or None
    profile.location = location or None
    profile.linkedin_url = linkedin_url or None
    profile.github_url = github_url or None
    profile.portfolio_url = portfolio_url or None
    profile.baseline_summary = baseline_summary or None
    db.commit()
    db.refresh(profile)
    return templates.TemplateResponse(
        request, "profile/edit.html", {"request": request, "profile": profile, "saved": True}
    )

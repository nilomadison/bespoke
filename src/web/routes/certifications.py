from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.session import get_session
from src.models.education import Certification
from src.web.deps import templates

router = APIRouter(prefix="/certifications", tags=["certifications"])


@router.get("/{cert_id}/view", response_class=HTMLResponse)
def get_cert_row(cert_id: int, request: Request, db: Session = Depends(get_session)):
    cert = db.get(Certification, cert_id)
    if cert is None:
        return HTMLResponse(content="", status_code=200)
    return templates.TemplateResponse(
        request, "education/_cert_row.html", {"request": request, "cert": cert}
    )


@router.post("/", response_class=HTMLResponse)
def create_certification(
    request: Request,
    db: Session = Depends(get_session),
    name: str = Form(...),
    issuer: str = Form(...),
    issue_date: str = Form(""),
    expiry_date: str = Form(""),
    credential_id: str = Form(""),
    credential_url: str = Form(""),
    notes: str = Form(""),
):
    cert = Certification(
        name=name,
        issuer=issuer,
        issue_date=date.fromisoformat(issue_date) if issue_date else None,
        expiry_date=date.fromisoformat(expiry_date) if expiry_date else None,
        credential_id=credential_id or None,
        credential_url=credential_url or None,
        notes=notes or None,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return templates.TemplateResponse(
        request, "education/_cert_row.html", {"request": request, "cert": cert}
    )


@router.get("/{cert_id}/edit", response_class=HTMLResponse)
def edit_cert_form(cert_id: int, request: Request, db: Session = Depends(get_session)):
    cert = db.get(Certification, cert_id)
    if cert is None:
        return HTMLResponse(content="Not found", status_code=404)
    return templates.TemplateResponse(
        request, "education/_cert_row_edit.html", {"request": request, "cert": cert}
    )


@router.post("/{cert_id}", response_class=HTMLResponse)
def update_certification(
    cert_id: int,
    request: Request,
    db: Session = Depends(get_session),
    name: str = Form(...),
    issuer: str = Form(...),
    issue_date: str = Form(""),
    expiry_date: str = Form(""),
    credential_id: str = Form(""),
    credential_url: str = Form(""),
    notes: str = Form(""),
):
    cert = db.get(Certification, cert_id)
    if cert is None:
        return HTMLResponse(content="Not found", status_code=404)
    cert.name = name
    cert.issuer = issuer
    cert.issue_date = date.fromisoformat(issue_date) if issue_date else None
    cert.expiry_date = date.fromisoformat(expiry_date) if expiry_date else None
    cert.credential_id = credential_id or None
    cert.credential_url = credential_url or None
    cert.notes = notes or None
    db.commit()
    db.refresh(cert)
    return templates.TemplateResponse(
        request, "education/_cert_row.html", {"request": request, "cert": cert}
    )


@router.post("/{cert_id}/delete", response_class=HTMLResponse)
def delete_certification(cert_id: int, db: Session = Depends(get_session)):
    cert = db.get(Certification, cert_id)
    if cert:
        db.delete(cert)
        db.commit()
    return HTMLResponse(content="", status_code=200)

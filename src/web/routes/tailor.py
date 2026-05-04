import asyncio
import io
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.session import get_session
from src.llm import get_llm_client
from src.llm.prompt_loader import get_prompt_hash
from src.models.profile import Profile
from src.models.tailoring import PlanItem, TailoringSession, TailoringStatus
from src.render.docx_renderer import docx_to_bytes, render_to_docx
from src.tailor.analyzer import analyze_job_description
from src.tailor.cover_letter import generate_cover_letter
from src.tailor.generator import generate_resume
from src.tailor.planner import build_plan
from src.tailor.resolver import resolve_items_for_display
from src.tailor.scorer import compute_match_score
from src.web.deps import templates

router = APIRouter(prefix="/tailor", tags=["tailor"])

# Background LLM calls run in a thread executor — keeps SQLite sync, async httpx async.
_executor = ThreadPoolExecutor(max_workers=2)


def _run_analysis_sync(session_id: int) -> None:
    asyncio.run(_run_analysis_async(session_id))


async def _run_analysis_async(session_id: int) -> None:
    """Full analysis pipeline: analyze JD → build plan → update session status."""
    from src.db.engine import SessionLocal

    db = SessionLocal()
    client = get_llm_client()
    try:
        session = db.get(TailoringSession, session_id)
        if session is None:
            return

        analysis, raw_json = await analyze_job_description(client, session.job_description)

        session.analysis_json = {
            "required_skills": analysis.required_skills,
            "preferred_skills": analysis.preferred_skills,
            "role_level": analysis.role_level,
            "domain": analysis.domain,
            "tone": analysis.tone,
            "impact_signals": analysis.impact_signals,
            "red_flags": analysis.red_flags,
            "emphasis_guidance": analysis.emphasis_guidance,
        }
        session.analysis_prompt_version = get_prompt_hash("analyze.system")
        session.status = TailoringStatus.ANALYZING
        db.commit()

        await build_plan(session_id, analysis, db, client)

        session = db.get(TailoringSession, session_id)
        session.status = TailoringStatus.ANALYZED
        db.commit()

    except Exception as e:
        session = db.get(TailoringSession, session_id)
        if session:
            session.status = TailoringStatus.DRAFT
            session.error_message = str(e)
            db.commit()
    finally:
        await client.close()
        db.close()


def _run_generation_sync(session_id: int) -> None:
    asyncio.run(_run_generation_async(session_id))


async def _run_generation_async(session_id: int) -> None:
    """Generation pipeline: resolve plan items → generate prose → update session status."""
    from src.db.engine import SessionLocal

    db = SessionLocal()
    client = get_llm_client()
    try:
        await generate_resume(session_id, db, client)

        session = db.get(TailoringSession, session_id)
        if session:
            session.status = TailoringStatus.GENERATED
            db.commit()

    except Exception as e:
        session = db.get(TailoringSession, session_id)
        if session:
            # Revert to PLAN_EDITED so the user can retry from the plan page
            session.status = TailoringStatus.PLAN_EDITED
            session.error_message = str(e)
            db.commit()
    finally:
        await client.close()
        db.close()


@router.get("/", response_class=HTMLResponse)
def tailor_index(request: Request, db: Session = Depends(get_session)):
    sessions = db.scalars(
        select(TailoringSession).order_by(TailoringSession.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request, "tailor/index.html", {"sessions": sessions}
    )


@router.get("/new", response_class=HTMLResponse)
def new_session_form(request: Request):
    return templates.TemplateResponse(request, "tailor/new.html")


@router.post("/", response_class=HTMLResponse)
def create_session(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    job_title: str = Form(...),
    company_name: str = Form(...),
    job_description: str = Form(...),
):
    session = TailoringSession(
        job_title=job_title,
        company_name=company_name,
        job_description=job_description,
        status=TailoringStatus.DRAFT,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    background_tasks.add_task(_run_analysis_sync, session.id)

    return RedirectResponse(url=f"/tailor/{session.id}/plan", status_code=303)


@router.get("/{session_id}/status", response_class=HTMLResponse)
def get_status(session_id: int, request: Request, db: Session = Depends(get_session)):
    """HTMX polling endpoint — returns spinner while working, triggers redirect when done."""
    session = db.get(TailoringSession, session_id)
    if session is None:
        return HTMLResponse(content="Session not found", status_code=404)

    if session.status in (TailoringStatus.ANALYZED, TailoringStatus.PLAN_EDITED):
        return HTMLResponse(
            content="",
            headers={"HX-Redirect": f"/tailor/{session_id}/plan"},
        )

    if session.status in (TailoringStatus.GENERATED, TailoringStatus.EXPORTED):
        return HTMLResponse(
            content="",
            headers={"HX-Redirect": f"/tailor/{session_id}/result"},
        )

    if session.status == TailoringStatus.DRAFT and session.error_message:
        return templates.TemplateResponse(
            request,
            "tailor/_status_error.html",
            {"session": session},
        )

    # ANALYZING or GENERATING — return spinner that re-polls
    return templates.TemplateResponse(
        request, "tailor/_status_spinner.html", {"session": session}
    )


@router.get("/{session_id}/plan", response_class=HTMLResponse)
def view_plan(session_id: int, request: Request, db: Session = Depends(get_session)):
    session = db.scalar(
        select(TailoringSession)
        .where(TailoringSession.id == session_id)
        .options(selectinload(TailoringSession.plan_items))
    )
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)
    score = compute_match_score(session.analysis_json, db) if session.analysis_json else None
    return templates.TemplateResponse(
        request, "tailor/plan.html", {"session": session, "score": score}
    )


@router.post("/{session_id}/plan/{item_id}/toggle", response_class=HTMLResponse)
def toggle_plan_item(
    session_id: int,
    item_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    item = db.get(PlanItem, item_id)
    if item is None or item.session_id != session_id:
        return HTMLResponse(content="Not found", status_code=404)
    item.include = not item.include
    session = db.get(TailoringSession, session_id)
    if session and session.status == TailoringStatus.ANALYZED:
        session.status = TailoringStatus.PLAN_EDITED
    db.commit()
    db.refresh(item)
    return templates.TemplateResponse(
        request, "tailor/_plan_item.html", {"item": item, "session_id": session_id}
    )


@router.post("/{session_id}/plan/{item_id}/note", response_class=HTMLResponse)
def update_plan_item_note(
    session_id: int,
    item_id: int,
    request: Request,
    db: Session = Depends(get_session),
    emphasis_note: str = Form(""),
):
    item = db.get(PlanItem, item_id)
    if item is None or item.session_id != session_id:
        return HTMLResponse(content="Not found", status_code=404)
    item.emphasis_note = emphasis_note.strip() or None
    session = db.get(TailoringSession, session_id)
    if session and session.status == TailoringStatus.ANALYZED:
        session.status = TailoringStatus.PLAN_EDITED
    db.commit()
    db.refresh(item)
    return templates.TemplateResponse(
        request, "tailor/_plan_item.html", {"item": item, "session_id": session_id}
    )


@router.post("/{session_id}/generate", response_class=HTMLResponse)
def start_generation(
    session_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    session = db.get(TailoringSession, session_id)
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)
    session.status = TailoringStatus.GENERATING
    session.error_message = None
    db.commit()
    background_tasks.add_task(_run_generation_sync, session_id)
    return RedirectResponse(url=f"/tailor/{session_id}/result", status_code=303)


@router.get("/{session_id}/result", response_class=HTMLResponse)
def view_result(session_id: int, request: Request, db: Session = Depends(get_session)):
    session = db.scalar(
        select(TailoringSession)
        .where(TailoringSession.id == session_id)
        .options(selectinload(TailoringSession.plan_items))
    )
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)
    resolved = resolve_items_for_display(session.plan_items, db)
    return templates.TemplateResponse(
        request, "tailor/result.html", {"session": session, "resolved_items": resolved}
    )


@router.post("/{session_id}/export")
def export_docx(session_id: int, db: Session = Depends(get_session)):
    session = db.get(TailoringSession, session_id)
    if session is None or not session.generated_json:
        return HTMLResponse(content="Not ready", status_code=400)

    profile = db.get(Profile, 1)
    profile_dict = {
        "full_name": profile.full_name if profile else "",
        "email": profile.email if profile else "",
        "phone": profile.phone if profile else None,
        "location": profile.location if profile else None,
        "linkedin_url": profile.linkedin_url if profile else None,
    }

    doc = render_to_docx(session.generated_json, profile_dict)
    data = docx_to_bytes(doc)

    safe_title = f"{session.company_name}_{session.job_title}".replace(" ", "_")
    filename = f"resume_{safe_title}.docx"

    if session.status == TailoringStatus.GENERATED:
        session.status = TailoringStatus.EXPORTED
        db.commit()

    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _run_cover_letter_sync(session_id: int) -> None:
    asyncio.run(_run_cover_letter_async(session_id))


async def _run_cover_letter_async(session_id: int) -> None:
    from src.db.engine import SessionLocal

    db = SessionLocal()
    client = get_llm_client()
    try:
        await generate_cover_letter(session_id, db, client)
    except Exception as e:
        session = db.get(TailoringSession, session_id)
        if session:
            session.cover_letter_generating = False
            session.error_message = str(e)
            db.commit()
    finally:
        await client.close()
        db.close()


@router.post("/{session_id}/cover-letter", response_class=HTMLResponse)
def start_cover_letter(
    session_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    session = db.get(TailoringSession, session_id)
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)
    if not session.generated_json:
        return HTMLResponse(content="Generate the resume first", status_code=400)
    session.cover_letter_generating = True
    session.cover_letter_json = None
    db.commit()
    background_tasks.add_task(_run_cover_letter_sync, session_id)
    return RedirectResponse(url=f"/tailor/{session_id}/cover-letter", status_code=303)


@router.get("/{session_id}/cover-letter", response_class=HTMLResponse)
def view_cover_letter(session_id: int, request: Request, db: Session = Depends(get_session)):
    session = db.get(TailoringSession, session_id)
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)
    return templates.TemplateResponse(
        request, "tailor/cover_letter.html", {"session": session}
    )


@router.get("/{session_id}/cover-letter/status", response_class=HTMLResponse)
def cover_letter_status(session_id: int, request: Request, db: Session = Depends(get_session)):
    """HTMX polling for cover letter generation."""
    session = db.get(TailoringSession, session_id)
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)
    if session.cover_letter_json:
        return HTMLResponse(
            content="",
            headers={"HX-Redirect": f"/tailor/{session_id}/cover-letter"},
        )
    return templates.TemplateResponse(
        request, "tailor/_cover_letter_spinner.html", {"session": session}
    )


@router.post("/{session_id}/delete", response_class=HTMLResponse)
def delete_session(session_id: int, db: Session = Depends(get_session)):
    session = db.get(TailoringSession, session_id)
    if session:
        db.delete(session)
        db.commit()
    return RedirectResponse(url="/tailor/", status_code=303)

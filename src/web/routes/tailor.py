import asyncio
import copy
import io
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.session import get_session
from src.llm import get_llm_client
from src.llm.prompt_loader import get_prompt_hash
from src.models.achievement import Achievement
from src.models.education import Certification, Education
from src.models.job import Job
from src.models.profile import Profile
from src.models.project import Project
from src.models.skill import Skill
from src.models.tailoring import PlanItem, PlanItemType, TailoringSession, TailoringStatus
from src.render.docx_renderer import docx_to_bytes, render_to_docx
from src.render.pdf_renderer import render_to_pdf
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


@router.get("/{session_id}/plan/add", response_class=HTMLResponse)
def plan_add_picker(
    session_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    """Return the inline picker fragment listing career items not already on the plan."""
    session = db.scalar(
        select(TailoringSession)
        .where(TailoringSession.id == session_id)
        .options(selectinload(TailoringSession.plan_items))
    )
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)

    used: dict[PlanItemType, set[int]] = {t: set() for t in PlanItemType}
    for item in session.plan_items:
        if item.reference_id is not None:
            used[item.item_type].add(item.reference_id)

    jobs = [j for j in db.scalars(select(Job).order_by(Job.sort_order, Job.id)).all()
            if j.id not in used[PlanItemType.JOB]]
    achievements = [a for a in db.scalars(select(Achievement).order_by(Achievement.id)).all()
                    if a.id not in used[PlanItemType.ACHIEVEMENT]]
    projects = [p for p in db.scalars(select(Project).order_by(Project.id)).all()
                if p.id not in used[PlanItemType.PROJECT]]
    educations = [e for e in db.scalars(select(Education).order_by(Education.id)).all()
                  if e.id not in used[PlanItemType.EDUCATION]]
    certifications = [c for c in db.scalars(select(Certification).order_by(Certification.id)).all()
                      if c.id not in used[PlanItemType.CERTIFICATION]]
    skills = db.scalars(select(Skill).order_by(Skill.name)).all()

    return templates.TemplateResponse(
        request,
        "tailor/_add_item_picker.html",
        {
            "session_id": session_id,
            "jobs": jobs,
            "achievements": achievements,
            "projects": projects,
            "educations": educations,
            "certifications": certifications,
            "skills": skills,
        },
    )


@router.post("/{session_id}/plan/add", response_class=HTMLResponse)
def plan_add_item(
    session_id: int,
    db: Session = Depends(get_session),
    item_type: str = Form(...),
    reference_id: int | None = Form(None),
    emphasis_note: str = Form(""),
):
    """Create a new PlanItem for an item the user wants to add."""
    session = db.scalar(
        select(TailoringSession)
        .where(TailoringSession.id == session_id)
        .options(selectinload(TailoringSession.plan_items))
    )
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)

    try:
        type_enum = PlanItemType(item_type)
    except ValueError:
        return HTMLResponse(content="Invalid item_type", status_code=400)

    note = emphasis_note.strip() or None

    # SKILL_GROUP carries the skill name(s) in emphasis_note and has reference_id=None.
    # All other types require a valid reference_id pointing to an existing record.
    if type_enum == PlanItemType.SKILL_GROUP:
        if not note:
            return HTMLResponse(content="emphasis_note is required for skill_group", status_code=400)
        ref_id = None
    else:
        if reference_id is None:
            return HTMLResponse(content="reference_id is required", status_code=400)
        model_for_type = {
            PlanItemType.JOB: Job,
            PlanItemType.ACHIEVEMENT: Achievement,
            PlanItemType.PROJECT: Project,
            PlanItemType.EDUCATION: Education,
            PlanItemType.CERTIFICATION: Certification,
        }[type_enum]
        target = db.get(model_for_type, reference_id)
        if target is None:
            return HTMLResponse(content="reference_id does not exist", status_code=400)
        ref_id = reference_id

    max_sort = max((i.sort_order for i in session.plan_items), default=-10)
    item = PlanItem(
        session_id=session_id,
        item_type=type_enum,
        reference_id=ref_id,
        include=True,
        emphasis_note=note,
        llm_rationale="Added by user",
        sort_order=max_sort + 10,
    )
    db.add(item)

    if session.status == TailoringStatus.ANALYZED:
        session.status = TailoringStatus.PLAN_EDITED
    db.commit()

    return HTMLResponse(
        content="",
        headers={"HX-Redirect": f"/tailor/{session_id}/plan"},
    )


@router.post("/{session_id}/plan/reorder")
async def reorder_plan_items(
    session_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    """Reorder plan items. Body: form-encoded `item_ids` list in new order."""
    form = await request.form()
    raw_ids = form.getlist("item_ids")
    try:
        new_order = [int(x) for x in raw_ids]
    except ValueError:
        return Response(content="Invalid item_ids", status_code=400)

    session = db.get(TailoringSession, session_id)
    if session is None:
        return Response(content="Not found", status_code=404)

    items = db.scalars(
        select(PlanItem).where(PlanItem.session_id == session_id)
    ).all()
    item_map = {i.id: i for i in items}

    if set(new_order) != set(item_map.keys()):
        return Response(content="item_ids must match the session's plan items", status_code=400)

    for index, item_id in enumerate(new_order):
        item_map[item_id].sort_order = index * 10

    if session.status == TailoringStatus.ANALYZED:
        session.status = TailoringStatus.PLAN_EDITED
    db.commit()
    return Response(status_code=204)


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


@router.post("/{session_id}/retry-analysis", response_class=HTMLResponse)
def retry_analysis(
    session_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    session = db.get(TailoringSession, session_id)
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)
    for item in list(session.plan_items):
        db.delete(item)
    session.analysis_json = None
    session.analysis_prompt_version = None
    session.error_message = None
    session.status = TailoringStatus.ANALYZING
    db.commit()
    background_tasks.add_task(_run_analysis_sync, session_id)
    return RedirectResponse(url=f"/tailor/{session_id}/plan", status_code=303)


@router.post("/{session_id}/retry-generation", response_class=HTMLResponse)
def retry_generation(
    session_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    session = db.get(TailoringSession, session_id)
    if session is None:
        return HTMLResponse(content="Not found", status_code=404)
    session.generated_json = None
    session.generation_prompt_version = None
    session.error_message = None
    session.status = TailoringStatus.GENERATING
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


# Allowed JSON paths for direct edits on `generated_json`. Tightly scoped to prevent
# arbitrary writes — anything outside this set is rejected with 400.
_ALLOWED_RESULT_PATHS = [
    re.compile(r"^summary$"),
    re.compile(r"^skills$"),
    re.compile(r"^experience\.\d+\.(title|company|dates)$"),
    re.compile(r"^experience\.\d+\.bullets\.\d+$"),
    re.compile(r"^projects\.\d+\.(name|description)$"),
    re.compile(r"^education\.\d+\.(degree|institution|dates)$"),
    re.compile(r"^certifications\.\d+\.(name|issuer|year)$"),
]


def _path_is_allowed(path: str) -> bool:
    return any(p.match(path) for p in _ALLOWED_RESULT_PATHS)


def _set_path(data: dict, path: str, value):
    """Set a value at a dotted path inside a nested dict/list. Numeric segments index lists."""
    parts = path.split(".")
    cursor = data
    for part in parts[:-1]:
        cursor = cursor[int(part)] if part.isdigit() else cursor[part]
    last = parts[-1]
    if last.isdigit():
        cursor[int(last)] = value
    else:
        cursor[last] = value


@router.post("/{session_id}/result/field", response_class=HTMLResponse)
def update_result_field(
    session_id: int,
    request: Request,
    db: Session = Depends(get_session),
    path: str = Form(...),
    value: str = Form(""),
):
    """Inline edit of a field inside generated_json. Validates path against allowlist."""
    session = db.get(TailoringSession, session_id)
    if session is None or not session.generated_json:
        return HTMLResponse(content="Not found", status_code=404)
    if not _path_is_allowed(path):
        return HTMLResponse(content="Invalid path", status_code=400)

    new_json = copy.deepcopy(session.generated_json)
    try:
        _set_path(new_json, path, value)
    except (KeyError, IndexError, TypeError):
        return HTMLResponse(content="Path does not resolve", status_code=400)

    session.generated_json = new_json
    db.commit()

    # Re-render the field fragment so HTMX can swap it back in display mode.
    parts = path.split(".")
    if path.startswith("experience.") and parts[2] == "bullets":
        ctx = {
            "session_id": session_id,
            "exp_index": int(parts[1]),
            "bullet_index": int(parts[3]),
            "value": value,
        }
        return templates.TemplateResponse(request, "tailor/_resume_bullet.html", ctx)

    # Field display class needs to match what result.html uses for that path.
    display_class = _display_class_for_path(path)
    kind = _kind_for_path(path)
    return templates.TemplateResponse(
        request,
        "tailor/_resume_field.html",
        {
            "session_id": session_id,
            "path": path,
            "value": value,
            "kind": kind,
            "display_class": display_class,
        },
    )


def _display_class_for_path(path: str) -> str:
    """Match the display-class choices in result.html / _resume_section.html."""
    if path == "summary":
        return "text-gray-800"
    if path == "skills":
        return "text-gray-700"
    if path.startswith("experience."):
        end = path.rsplit(".", 1)[-1]
        if end == "title":
            return "font-semibold text-gray-900"
        if end == "dates":
            return "text-sm text-gray-400"
        if end == "company":
            return "text-sm text-gray-500"
    if path.startswith("projects."):
        end = path.rsplit(".", 1)[-1]
        return "font-semibold text-gray-900" if end == "name" else "text-gray-700"
    if path.startswith("education.") or path.startswith("certifications."):
        end = path.rsplit(".", 1)[-1]
        if end in ("degree", "name"):
            return "font-semibold text-gray-900"
        if end in ("institution", "issuer"):
            return "text-gray-500"
        if end in ("dates", "year"):
            return "text-gray-400 text-sm"
    return "text-gray-700"


def _kind_for_path(path: str) -> str:
    if path == "summary" or path == "skills":
        return "textarea"
    if path.startswith("projects.") and path.endswith(".description"):
        return "textarea"
    return "text"


@router.post("/{session_id}/result/bullet/add", response_class=HTMLResponse)
def add_result_bullet(
    session_id: int,
    request: Request,
    db: Session = Depends(get_session),
    experience_index: int = Form(...),
):
    session = db.get(TailoringSession, session_id)
    if session is None or not session.generated_json:
        return HTMLResponse(content="Not found", status_code=404)

    new_json = copy.deepcopy(session.generated_json)
    experience = new_json.get("experience") or []
    if experience_index < 0 or experience_index >= len(experience):
        return HTMLResponse(content="experience_index out of range", status_code=400)

    experience[experience_index].setdefault("bullets", []).append("")
    session.generated_json = new_json
    db.commit()

    return templates.TemplateResponse(
        request,
        "tailor/_resume_bullets_list.html",
        {
            "session_id": session_id,
            "exp_index": experience_index,
            "bullets": experience[experience_index]["bullets"],
        },
    )


@router.post("/{session_id}/result/bullet/delete", response_class=HTMLResponse)
def delete_result_bullet(
    session_id: int,
    request: Request,
    db: Session = Depends(get_session),
    experience_index: int = Form(...),
    bullet_index: int = Form(...),
):
    session = db.get(TailoringSession, session_id)
    if session is None or not session.generated_json:
        return HTMLResponse(content="Not found", status_code=404)

    new_json = copy.deepcopy(session.generated_json)
    experience = new_json.get("experience") or []
    if experience_index < 0 or experience_index >= len(experience):
        return HTMLResponse(content="experience_index out of range", status_code=400)

    bullets = experience[experience_index].get("bullets") or []
    if bullet_index < 0 or bullet_index >= len(bullets):
        return HTMLResponse(content="bullet_index out of range", status_code=400)

    bullets.pop(bullet_index)
    session.generated_json = new_json
    db.commit()

    return templates.TemplateResponse(
        request,
        "tailor/_resume_bullets_list.html",
        {
            "session_id": session_id,
            "exp_index": experience_index,
            "bullets": bullets,
        },
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


def _profile_dict(db: Session) -> dict:
    profile = db.get(Profile, 1)
    return {
        "full_name": profile.full_name if profile else "",
        "email": profile.email if profile else "",
        "phone": profile.phone if profile else None,
        "location": profile.location if profile else None,
        "linkedin_url": profile.linkedin_url if profile else None,
    }


@router.get("/{session_id}/export.pdf")
def export_pdf(session_id: int, db: Session = Depends(get_session)):
    session = db.get(TailoringSession, session_id)
    if session is None or not session.generated_json:
        return HTMLResponse(content="Not ready", status_code=400)

    pdf_bytes = render_to_pdf(session.generated_json, _profile_dict(db))

    safe_title = f"{session.company_name}_{session.job_title}".replace(" ", "_")
    filename = f"resume_{safe_title}.pdf"

    if session.status == TailoringStatus.GENERATED:
        session.status = TailoringStatus.EXPORTED
        db.commit()

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
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

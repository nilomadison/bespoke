import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.llm.client import LLMClient
from src.llm.mock_client import MockLLMClient
from src.llm.parse import parse_llm_json
from src.llm.prompt_loader import get_prompt_hash, load_prompt
from src.models.achievement import Achievement
from src.models.education import Certification, Education
from src.models.job import Job
from src.models.project import Project
from src.models.tailoring import PlanItemType, TailoringSession


def resolve_plan_items(session: TailoringSession, db: Session) -> dict:
    """Build the context dict passed to the generate prompt.

    Resolves each included PlanItem to its actual DB record and groups
    achievements under their parent job. Only included items are returned.
    """
    included = [item for item in session.plan_items if item.include]

    job_plan_items = {i.reference_id: i for i in included if i.item_type == PlanItemType.JOB}
    ach_plan_items = [i for i in included if i.item_type == PlanItemType.ACHIEVEMENT]
    sg_plan_items = [i for i in included if i.item_type == PlanItemType.SKILL_GROUP]
    proj_plan_items = [i for i in included if i.item_type == PlanItemType.PROJECT]
    edu_plan_items = [i for i in included if i.item_type == PlanItemType.EDUCATION]
    cert_plan_items = [i for i in included if i.item_type == PlanItemType.CERTIFICATION]

    # Load achievements and discover their parent job IDs
    ach_ids = [i.reference_id for i in ach_plan_items if i.reference_id]
    achievements_by_id: dict[int, Achievement] = {}
    if ach_ids:
        achs = db.scalars(select(Achievement).where(Achievement.id.in_(ach_ids))).all()
        achievements_by_id = {a.id: a for a in achs}

    # Collect all job IDs needed (explicit job items + implicit from achievements)
    all_job_ids: set[int] = set(job_plan_items.keys())
    for ach_item in ach_plan_items:
        if ach_item.reference_id and ach_item.reference_id in achievements_by_id:
            all_job_ids.add(achievements_by_id[ach_item.reference_id].job_id)

    # Load jobs
    jobs_by_id: dict[int, Job] = {}
    if all_job_ids:
        jobs = db.scalars(select(Job).where(Job.id.in_(all_job_ids))).all()
        jobs_by_id = {j.id: j for j in jobs}

    # Build experience list in plan order; implicit jobs go last
    job_ids_ordered = list(job_plan_items.keys())
    for ach_item in ach_plan_items:
        if ach_item.reference_id and ach_item.reference_id in achievements_by_id:
            jid = achievements_by_id[ach_item.reference_id].job_id
            if jid not in job_ids_ordered:
                job_ids_ordered.append(jid)

    experiences = []
    for job_id in job_ids_ordered:
        job = jobs_by_id.get(job_id)
        if job is None:
            continue

        job_plan_item = job_plan_items.get(job_id)

        selected_achievements = [
            i
            for i in ach_plan_items
            if i.reference_id in achievements_by_id
            and achievements_by_id[i.reference_id].job_id == job_id
        ]

        ach_rows = []
        for ach_item in selected_achievements:
            ach = achievements_by_id.get(ach_item.reference_id)
            if ach is None:
                continue
            row: dict = {"id": ach.id, "text": ach.text}
            if ach.metric:
                row["metric"] = ach.metric
            if ach_item.emphasis_note:
                row["emphasis_note"] = ach_item.emphasis_note
            ach_rows.append(row)

        exp: dict = {
            "job": {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "start_date": job.start_date.strftime("%b %Y") if job.start_date else None,
                "end_date": job.end_date.strftime("%b %Y") if job.end_date else "Present",
                "summary": job.summary,
            },
            "selected_achievements": ach_rows,
        }
        if job_plan_item and job_plan_item.emphasis_note:
            exp["emphasis_note"] = job_plan_item.emphasis_note
        experiences.append(exp)

    # Skill group (first one wins if multiple)
    skill_group = None
    if sg_plan_items:
        sg = sg_plan_items[0]
        skill_group = {"skills": sg.emphasis_note or ""}

    # Projects
    project_rows = []
    if proj_plan_items:
        proj_ids = [i.reference_id for i in proj_plan_items if i.reference_id]
        projs_by_id = {
            p.id: p for p in db.scalars(select(Project).where(Project.id.in_(proj_ids))).all()
        }
        for pitem in proj_plan_items:
            proj = projs_by_id.get(pitem.reference_id)
            if proj is None:
                continue
            row = {"id": proj.id, "name": proj.name, "summary": proj.summary}
            if proj.description:
                row["description"] = proj.description
            if pitem.emphasis_note:
                row["emphasis_note"] = pitem.emphasis_note
            project_rows.append(row)

    # Education
    edu_rows = []
    if edu_plan_items:
        edu_ids = [i.reference_id for i in edu_plan_items if i.reference_id]
        edus_by_id = {
            e.id: e for e in db.scalars(select(Education).where(Education.id.in_(edu_ids))).all()
        }
        for eitem in edu_plan_items:
            edu = edus_by_id.get(eitem.reference_id)
            if edu is None:
                continue
            field_suffix = f" in {edu.field}" if edu.field else ""
            row = {
                "id": edu.id,
                "institution": edu.institution,
                "degree": f"{edu.degree}{field_suffix}",
                "end_date": edu.end_date.strftime("%Y") if edu.end_date else None,
                "honors": edu.honors,
            }
            edu_rows.append(row)

    # Certifications
    cert_rows = []
    if cert_plan_items:
        cert_ids = [i.reference_id for i in cert_plan_items if i.reference_id]
        certs_by_id = {
            c.id: c
            for c in db.scalars(select(Certification).where(Certification.id.in_(cert_ids))).all()
        }
        for citem in cert_plan_items:
            cert = certs_by_id.get(citem.reference_id)
            if cert is None:
                continue
            row = {"id": cert.id, "name": cert.name, "issuer": cert.issuer}
            if cert.issue_date:
                row["issue_date"] = cert.issue_date.isoformat()
            cert_rows.append(row)

    return {
        "experiences": experiences,
        "skill_group": skill_group,
        "projects": project_rows,
        "education": edu_rows,
        "certifications": cert_rows,
    }


async def generate_resume(
    session_id: int,
    db: Session,
    client: LLMClient | MockLLMClient,
) -> dict:
    """Stage 2: generate resume prose from the approved plan items.

    Loads the session with plan items, resolves them to DB records, calls the
    generate LLM, parses the response, and stores the result on the session.
    Returns the parsed generation dict.
    """
    session = db.scalar(
        select(TailoringSession)
        .where(TailoringSession.id == session_id)
        .options(selectinload(TailoringSession.plan_items))
    )
    if session is None:
        raise ValueError(f"Session {session_id} not found")

    plan_context = resolve_plan_items(session, db)

    system_prompt = load_prompt("generate.system")
    user_message = load_prompt("generate.user").format(
        job_title=session.job_title,
        company_name=session.company_name,
        analysis_json=json.dumps(session.analysis_json or {}, indent=2),
        plan_context=json.dumps(plan_context, indent=2),
    )

    raw = await client.chat(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.4,
        max_tokens=8192,
    )

    result = parse_llm_json(raw, "generate")

    _REQUIRED_GENERATE_FIELDS = ("summary", "experience", "skills", "projects", "education")
    missing = [f for f in _REQUIRED_GENERATE_FIELDS if f not in result]
    if missing:
        raise ValueError(
            f"[generate] LLM response missing required fields: {missing}. "
            f"Got keys: {list(result.keys())}"
        )

    session.generated_json = result
    session.generation_prompt_version = get_prompt_hash("generate.system")
    db.commit()

    return result

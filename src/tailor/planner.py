import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.llm.client import LLMClient
from src.llm.mock_client import MockLLMClient
from src.llm.prompt_loader import load_prompt
from src.models.achievement import Achievement
from src.models.education import Certification, Education
from src.models.job import Job
from src.models.project import Project
from src.models.skill import Skill
from src.models.tailoring import PlanItem, PlanItemType, TailoringSession
from src.tailor.analyzer import JobAnalysis, _strip_fences


def serialize_career(db: Session) -> dict:
    """Serialize the full career database as a JSON-friendly dict for the planner LLM."""
    jobs = db.scalars(
        select(Job)
        .options(selectinload(Job.achievements), selectinload(Job.job_skills))
        .order_by(Job.sort_order, Job.start_date.desc())
    ).all()

    skills = db.scalars(select(Skill).order_by(Skill.category, Skill.name)).all()
    projects = db.scalars(
        select(Project).order_by(Project.prominence.desc(), Project.name)
    ).all()
    education = db.scalars(
        select(Education).order_by(Education.end_date.desc())
    ).all()
    certifications = db.scalars(
        select(Certification).order_by(Certification.issue_date.desc())
    ).all()

    return {
        "jobs": [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "start_date": j.start_date.isoformat() if j.start_date else None,
                "end_date": j.end_date.isoformat() if j.end_date else None,
                "is_technical": j.is_technical,
                "summary": j.summary,
                "achievements": [
                    {
                        "id": a.id,
                        "text": a.text,
                        "metric": a.metric,
                        "impact_tags": a.impact_tags,
                        "prominence": a.prominence,
                    }
                    for a in j.achievements
                ],
            }
            for j in jobs
        ],
        "skills": [
            {"id": s.id, "name": s.name, "category": s.category} for s in skills
        ],
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "summary": p.summary,
                "description": p.description,
                "prominence": p.prominence,
                "is_active": p.is_active,
                "start_date": p.start_date.isoformat() if p.start_date else None,
            }
            for p in projects
        ],
        "education": [
            {
                "id": e.id,
                "institution": e.institution,
                "degree": e.degree,
                "field": e.field,
                "location": e.location,
                "start_date": e.start_date.isoformat() if e.start_date else None,
                "end_date": e.end_date.isoformat() if e.end_date else None,
                "is_in_progress": e.is_in_progress,
                "expected_end_date": (
                    e.expected_end_date.isoformat() if e.expected_end_date else None
                ),
                "honors": e.honors,
                "gpa": e.gpa,
            }
            for e in education
        ],
        "certifications": [
            {
                "id": c.id,
                "name": c.name,
                "issuer": c.issuer,
                "issue_date": c.issue_date.isoformat() if c.issue_date else None,
            }
            for c in certifications
        ],
    }


async def build_plan(
    session_id: int,
    analysis: JobAnalysis,
    db: Session,
    client: LLMClient | MockLLMClient,
) -> list[PlanItem]:
    """Stage 1b: given the job analysis, select and order career items.

    Queries the career database, calls the planner LLM, and persists PlanItems.
    """
    career_context = serialize_career(db)

    system_prompt = load_prompt("plan.system")
    user_message = load_prompt("plan.user").format(
        analysis_json=json.dumps(
            {
                "required_skills": analysis.required_skills,
                "preferred_skills": analysis.preferred_skills,
                "role_level": analysis.role_level,
                "domain": analysis.domain,
                "tone": analysis.tone,
                "impact_signals": analysis.impact_signals,
                "red_flags": analysis.red_flags,
                "emphasis_guidance": analysis.emphasis_guidance,
            },
            indent=2,
        ),
        career_context=json.dumps(career_context, indent=2),
    )

    raw = await client.chat(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.3,
        max_tokens=4096,
    )

    cleaned = _strip_fences(raw)
    plan_data = json.loads(cleaned)

    items = []
    for idx, row in enumerate(plan_data.get("items", [])):
        item_type_str = row.get("type", "")
        try:
            item_type = PlanItemType(item_type_str)
        except ValueError:
            continue  # skip unrecognized types rather than crash

        items.append(
            PlanItem(
                session_id=session_id,
                item_type=item_type,
                reference_id=row.get("id"),
                include=True,
                emphasis_note=row.get("emphasis_note"),
                llm_rationale=row.get("rationale"),
                sort_order=idx,
            )
        )

    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items

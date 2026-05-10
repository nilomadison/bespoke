import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.llm.client import LLMClient
from src.llm.mock_client import MockLLMClient
from src.llm.parse import parse_llm_json
from src.llm.prompt_loader import load_prompt
from src.models.profile import Profile
from src.models.tailoring import TailoringSession
from src.tailor.generator import resolve_plan_items


async def generate_cover_letter(
    session_id: int,
    db: Session,
    client: LLMClient | MockLLMClient,
) -> dict:
    """Generate a cover letter from the approved plan items.

    Re-uses the same plan context as the resume generator so that
    all claims in the letter are traceable to the same DB data.
    Stores the result on session.cover_letter_json and returns it.
    """
    session = db.scalar(
        select(TailoringSession)
        .where(TailoringSession.id == session_id)
        .options(selectinload(TailoringSession.plan_items))
    )
    if session is None:
        raise ValueError(f"Session {session_id} not found")

    plan_context = resolve_plan_items(session, db)

    profile = db.get(Profile, 1)
    baseline_summary = (profile.baseline_summary or "").strip() if profile else ""

    system_prompt = load_prompt("cover_letter.system")
    user_message = load_prompt("cover_letter.user").format(
        job_title=session.job_title,
        company_name=session.company_name,
        analysis_json=json.dumps(session.analysis_json or {}, indent=2),
        plan_context=json.dumps(plan_context, indent=2),
        baseline_summary=baseline_summary,
    )

    raw = await client.chat(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.5,
        max_tokens=10240,
    )

    result = parse_llm_json(raw, "cover_letter")

    session.cover_letter_json = result
    session.cover_letter_generating = False
    db.commit()

    return result

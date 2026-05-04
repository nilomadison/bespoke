import json
from dataclasses import dataclass, field

from src.llm.client import LLMClient
from src.llm.mock_client import MockLLMClient
from src.llm.prompt_loader import load_prompt


@dataclass
class JobAnalysis:
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    role_level: str = ""
    domain: str = ""
    tone: str = ""
    impact_signals: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    emphasis_guidance: str = ""


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences that models sometimes wrap JSON in."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.endswith("```"):
            s = s[: s.rfind("```")]
    return s.strip()


async def analyze_job_description(
    client: LLMClient | MockLLMClient,
    job_description: str,
) -> tuple[JobAnalysis, str]:
    """Stage 1: extract structured signals from a job description.

    Returns (parsed JobAnalysis, raw JSON string for storage).
    """
    system_prompt = load_prompt("analyze.system")
    user_message = load_prompt("analyze.user").format(job_description=job_description)

    raw = await client.chat(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.2,
    )

    cleaned = _strip_fences(raw)
    data = json.loads(cleaned)

    analysis = JobAnalysis(
        required_skills=data.get("required_skills", []),
        preferred_skills=data.get("preferred_skills", []),
        role_level=data.get("role_level", ""),
        domain=data.get("domain", ""),
        tone=data.get("tone", ""),
        impact_signals=data.get("impact_signals", []),
        red_flags=data.get("red_flags", []),
        emphasis_guidance=data.get("emphasis_guidance", ""),
    )
    return analysis, cleaned

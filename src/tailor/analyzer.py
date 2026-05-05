import json
import logging
from dataclasses import dataclass, field

from src.llm.client import LLMClient
from src.llm.mock_client import MockLLMClient
from src.llm.parse import parse_llm_json
from src.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

VALID_ROLE_LEVELS = frozenset({
    "junior", "mid", "senior", "staff", "lead", "principal", "manager", "director"
})

VALID_IMPACT_SIGNALS = frozenset({
    "scale", "reliability", "speed", "cost_reduction", "revenue",
    "developer_experience", "leadership", "mentorship", "architecture",
    "security", "data", "ml", "product", "ux", "cross_functional",
    "communication", "ownership", "scrappiness", "research",
})


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
    """Backward-compat shim — tests import this directly. Use parse_llm_json for new code."""
    import re
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
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

    data = parse_llm_json(raw, "analyze")

    raw_level = data.get("role_level", "").lower()
    if raw_level and raw_level not in VALID_ROLE_LEVELS:
        logger.warning("[analyze] role_level %r not in allowed vocabulary", raw_level)

    raw_signals = data.get("impact_signals", [])
    impact_signals = [s for s in raw_signals if s in VALID_IMPACT_SIGNALS]
    unknown_signals = [s for s in raw_signals if s not in VALID_IMPACT_SIGNALS]
    if unknown_signals:
        logger.warning("[analyze] impact_signals contained unknown tokens: %r", unknown_signals)

    analysis = JobAnalysis(
        required_skills=data.get("required_skills", []),
        preferred_skills=data.get("preferred_skills", []),
        role_level=raw_level,
        domain=data.get("domain", ""),
        tone=data.get("tone", ""),
        impact_signals=impact_signals,
        red_flags=data.get("red_flags", []),
        emphasis_guidance=data.get("emphasis_guidance", ""),
    )
    return analysis, json.dumps(data)

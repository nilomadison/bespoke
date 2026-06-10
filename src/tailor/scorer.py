"""Heuristic profile-to-job match scoring. No LLM call — computed from DB + analysis_json."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.job import Job
from src.models.skill import Skill


@dataclass
class SkillCoverage:
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def pct(self) -> int:
        total = len(self.matched) + len(self.missing)
        return int(len(self.matched) / total * 100) if total else 100


@dataclass
class MatchScore:
    required: SkillCoverage
    preferred: SkillCoverage
    role_level_note: str | None
    domain_match: bool


# Map seniority keywords to a numeric rank for comparison
_SENIORITY_RANK: dict[str, int] = {
    "junior": 1,
    "associate": 1,
    "mid": 2,
    "senior": 3,
    "lead": 4,
    "staff": 4,
    "principal": 5,
    "architect": 5,
    "manager": 4,
    "director": 6,
    "vp": 7,
    "cto": 8,
}

_TITLE_KEYWORDS = frozenset(_SENIORITY_RANK)

_TECHNICAL_DOMAINS = frozenset(
    {"backend", "frontend", "fullstack", "mobile", "devops", "ml", "data", "security"}
)


def _skill_matches(candidate_skills: set[str], target: str) -> bool:
    """Case-insensitive substring match in either direction."""
    t = target.lower()
    for s in candidate_skills:
        if t in s or s in t:
            return True
    return False


def _best_seniority(jobs: list[Job]) -> tuple[str | None, int]:
    """Return the highest seniority keyword + rank found across all job titles."""
    best_kw, best_rank = None, 0
    for job in jobs:
        title_lower = job.title.lower()
        for kw in _TITLE_KEYWORDS:
            if kw in title_lower:
                rank = _SENIORITY_RANK[kw]
                if rank > best_rank:
                    best_rank = rank
                    best_kw = kw
    return best_kw, best_rank


def compute_match_score(analysis_json: dict, db: Session) -> MatchScore:
    """Compute a structured skill/role match without calling the LLM.

    Matches required and preferred skills from the job analysis against skills
    in the candidate DB using case-insensitive substring matching.
    """
    required_raw: list[str] = analysis_json.get("required_skills", [])
    preferred_raw: list[str] = analysis_json.get("preferred_skills", [])
    role_level: str = analysis_json.get("role_level", "").lower()
    domain: str = analysis_json.get("domain", "").lower()

    # Candidate skill set (lowercase names for matching)
    skills = db.scalars(select(Skill)).all()
    candidate_skills = {s.name.lower() for s in skills}

    # Required skill match
    req_matched, req_missing = [], []
    for skill in required_raw:
        (req_matched if _skill_matches(candidate_skills, skill) else req_missing).append(skill)

    # Preferred skill match
    pref_matched, pref_missing = [], []
    for skill in preferred_raw:
        (pref_matched if _skill_matches(candidate_skills, skill) else pref_missing).append(skill)

    # Role level note: compare JD level vs. highest title seniority in DB
    jobs = db.scalars(select(Job)).all()
    candidate_kw, candidate_rank = _best_seniority(jobs)
    jd_rank = _SENIORITY_RANK.get(role_level, 2)

    role_level_note = None
    if role_level and candidate_kw:
        if candidate_rank > jd_rank + 1:
            role_level_note = (
                f"Your titles suggest {candidate_kw}-level experience — "
                f"consider whether the framing matches the {role_level} scope of this role."
            )
        elif jd_rank > candidate_rank + 1:
            role_level_note = (
                f"This role targets {role_level} level — "
                f"emphasize scope, ownership, and impact to bridge the gap."
            )

    # Domain match: does the candidate have technical jobs for technical domains?
    domain_match = True
    if domain in _TECHNICAL_DOMAINS:
        domain_match = any(j.is_technical for j in jobs)

    return MatchScore(
        required=SkillCoverage(matched=req_matched, missing=req_missing),
        preferred=SkillCoverage(matched=pref_matched, missing=pref_missing),
        role_level_note=role_level_note,
        domain_match=domain_match,
    )

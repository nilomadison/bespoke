import hashlib
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a prompt file from prompts/ by dotted name.

    Example: load_prompt("analyze.system") loads prompts/analyze/system.md
    Cached after first read. Call load_prompt.cache_clear() after editing prompts.
    """
    path = PROMPTS_DIR / Path(*name.split(".")).with_suffix(".md")
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def get_prompt_hash(name: str) -> str:
    """Return sha256 hex digest of the prompt file bytes.

    Reliable even for uncommitted edits. Stored in TailoringSession to record
    exactly which prompt version produced a given result.
    """
    path = PROMPTS_DIR / Path(*name.split(".")).with_suffix(".md")
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]

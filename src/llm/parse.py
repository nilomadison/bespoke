import json
import logging
import re

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str, stage: str) -> dict:
    """Strip markdown fences from a raw LLM response and parse JSON.

    Handles both plain ``` and language-tagged ```json fences. Logs the full
    raw output at ERROR level on failure so the bad response is always
    capturable without reproducing the exact LLM call.
    """
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
    if s.endswith("```"):
        s = s[: s.rfind("```")]
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError as exc:
        logger.error(
            "[%s] Failed to parse LLM JSON. Raw output:\n%s",
            stage,
            raw,
        )
        raise ValueError(f"[{stage}] LLM returned non-JSON output: {exc}") from exc

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


class MockLLMClient:
    """Returns canned fixture JSON for UI testing without hitting the API.

    Used when BESPOKE_MOCK_LLM=1. Detects which prompt is being called by
    inspecting keywords in the system prompt.
    """

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        prompt_lower = system_prompt.lower()
        # Check most-specific patterns first to avoid substring false positives.
        # "explanation" contains "plan"; "resume writer" is unique to generate/system.md.
        if "cover letter writer" in prompt_lower:
            return (FIXTURES_DIR / "sample_cover_letter.json").read_text()
        if "resume writer" in prompt_lower:
            return (FIXTURES_DIR / "sample_generation.json").read_text()
        if "analyst" in prompt_lower or "extract" in prompt_lower:
            return (FIXTURES_DIR / "sample_analysis.json").read_text()
        if "strategist" in prompt_lower or "plan" in prompt_lower or "select" in prompt_lower:
            return (FIXTURES_DIR / "sample_plan.json").read_text()
        # Fallback — return empty object so callers don't crash
        return "{}"

    async def close(self) -> None:
        pass

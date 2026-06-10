import asyncio
import json

import pytest

from src.llm.mock_client import MockLLMClient
from src.tailor.analyzer import JobAnalysis, _strip_fences, analyze_job_description


def test_strip_fences_plain():
    assert _strip_fences('{"a":1}') == '{"a":1}'


def test_strip_fences_with_json_fence():
    raw = '```json\n{"a":1}\n```'
    assert _strip_fences(raw) == '{"a":1}'


def test_strip_fences_with_bare_fence():
    raw = '```\n{"a":1}\n```'
    assert _strip_fences(raw) == '{"a":1}'


def test_analyze_returns_job_analysis():
    client = MockLLMClient()
    analysis, raw = asyncio.run(analyze_job_description(client, "some job description"))

    assert isinstance(analysis, JobAnalysis)
    assert isinstance(raw, str)
    data = json.loads(raw)
    assert "required_skills" in data


def test_analyze_populates_all_fields():
    client = MockLLMClient()
    analysis, _ = asyncio.run(analyze_job_description(client, "some job description"))

    assert "Python" in analysis.required_skills
    assert analysis.role_level == "senior"
    assert analysis.domain == "backend"
    assert analysis.tone == "startup-casual"
    assert len(analysis.impact_signals) > 0
    assert analysis.emphasis_guidance != ""


def test_analyze_bad_json_raises():
    class BadClient:
        async def chat(self, **kwargs):
            return "not json at all"

        async def close(self):
            pass

    with pytest.raises(ValueError):
        asyncio.run(analyze_job_description(BadClient(), "jd"))


def test_analyze_fenced_json_parses():
    fixture_data = {
        "required_skills": ["Go"],
        "preferred_skills": [],
        "role_level": "mid",
        "domain": "platform",
        "tone": "formal",
        "impact_signals": ["reliability"],
        "red_flags": [],
        "emphasis_guidance": "Focus on Go experience.",
    }

    class FencedClient:
        async def chat(self, **kwargs):
            return f"```json\n{json.dumps(fixture_data)}\n```"

        async def close(self):
            pass

    analysis, raw = asyncio.run(analyze_job_description(FencedClient(), "jd"))
    assert analysis.role_level == "mid"
    assert json.loads(raw) == fixture_data

"""
Tests for Settings env-var parsing.

BESPOKE_MOCK_LLM is documented as `BESPOKE_MOCK_LLM=1` in the README, so the
parser must accept truthy variants, not just the literal "true".
"""

import pytest

from src.config import Settings


@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", " 1 "])
def test_mock_llm_truthy_values(monkeypatch, value):
    monkeypatch.setenv("BESPOKE_MOCK_LLM", value)
    assert Settings().mock_llm is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_mock_llm_falsy_values(monkeypatch, value):
    monkeypatch.setenv("BESPOKE_MOCK_LLM", value)
    assert Settings().mock_llm is False


def test_mock_llm_defaults_off(monkeypatch):
    monkeypatch.delenv("BESPOKE_MOCK_LLM", raising=False)
    assert Settings().mock_llm is False

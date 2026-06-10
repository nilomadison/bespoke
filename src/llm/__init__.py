from src.config import settings

from .client import LLMClient
from .mock_client import MockLLMClient


def get_llm_client() -> LLMClient | MockLLMClient:
    if settings.mock_llm:
        return MockLLMClient()
    return LLMClient()

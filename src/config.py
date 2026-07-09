import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a local .env into the process environment before Settings
# reads them. Called at import time so every entry point (web server, seed CLI,
# alembic, prompt_compare, tests) picks up .env, not just uvicorn.
load_dotenv()


@dataclass
class Settings:
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    default_model: str = field(
        default_factory=lambda: os.getenv("DEFAULT_MODEL", "anthropic/claude-sonnet-4-6")
    )
    data_dir: str = field(default_factory=lambda: os.getenv("DATA_DIR", "data"))
    db_echo: bool = field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() == "true")
    mock_llm: bool = field(
        default_factory=lambda: os.getenv("BESPOKE_MOCK_LLM", "").strip().lower()
        in ("1", "true", "yes")
    )
    app_title: str = "Bespoke"

    @property
    def db_path(self) -> Path:
        p = Path(self.data_dir) / "bespoke.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()

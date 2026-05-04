import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )
    )
    default_model: str = field(
        default_factory=lambda: os.getenv("DEFAULT_MODEL", "anthropic/claude-3.5-sonnet")
    )
    data_dir: str = field(default_factory=lambda: os.getenv("DATA_DIR", "data"))
    db_echo: bool = field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() == "true")
    mock_llm: bool = field(
        default_factory=lambda: os.getenv("BESPOKE_MOCK_LLM", "false").lower() == "true"
    )
    app_title: str = "Bespoke"

    @property
    def db_path(self) -> Path:
        p = Path(self.data_dir) / "bespoke.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()

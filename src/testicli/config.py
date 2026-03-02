"""Configuration management for testicli."""


import os
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_MODEL = "claude-sonnet-4-20250514"
AGENT_DIR = ".testicli"


class Settings(BaseModel):
    anthropic_api_key: str = Field(default="")
    model: str = Field(default=DEFAULT_MODEL)
    max_fix_attempts: int = Field(default=2)
    code_temperature: float = Field(default=0.0)
    analysis_temperature: float = Field(default=0.3)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("TEST_AGENT_MODEL", DEFAULT_MODEL),
            max_fix_attempts=int(os.environ.get("TEST_AGENT_MAX_FIX_ATTEMPTS", "2")),
        )


def get_agent_dir(project_root: Path) -> Path:
    return project_root / AGENT_DIR


def ensure_agent_dir(project_root: Path) -> Path:
    agent_dir = get_agent_dir(project_root)
    agent_dir.mkdir(exist_ok=True)
    (agent_dir / "plans").mkdir(exist_ok=True)
    (agent_dir / "failures").mkdir(exist_ok=True)
    return agent_dir

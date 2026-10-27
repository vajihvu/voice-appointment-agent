"""Application configuration loader using Pydantic Settings and YAML files."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Safely loads a YAML file if it exists, otherwise returns an empty dict."""
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    """Central configuration class loading environment variables and YAML settings."""

    # Server configuration
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    BASE_URL: str = "http://localhost:8000"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Plivo Telephony & SMS
    PLIVO_AUTH_ID: str = ""
    PLIVO_AUTH_TOKEN: str = ""
    PLIVO_PHONE_NUMBER: str = ""
    HUMAN_HANDOFF_NUMBER: str = "+919876543210"

    # STT (Deepgram)
    DEEPGRAM_API_KEY: str = ""

    # LLM (OpenAI-compatible)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"

    # TTS (Deepgram Aura)
    TTS_MODEL: str = "aura-asteria-en"

    # Persistence
    DATABASE_URL: str = "sqlite+aiosqlite:///./voice_agent.db"
    TRANSCRIPT_RETENTION_DAYS: int = 30

    # Feature Toggles
    ENABLE_SMS_CONFIRMATION: bool = True
    ENABLE_WEBHOOK_SIGNATURE_VERIFICATION: bool = True


    # Loaded from YAML
    business: Dict[str, Any] = Field(default_factory=dict)
    services: List[Dict[str, Any]] = Field(default_factory=list)
    human_handoff: Dict[str, Any] = Field(default_factory=dict)
    barge_in: Dict[str, Any] = Field(default_factory=dict)
    sms_config: Dict[str, Any] = Field(default_factory=dict)
    privacy_config: Dict[str, Any] = Field(default_factory=dict)
    prompts: Dict[str, Any] = Field(default_factory=dict)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def load_business_configs(self) -> None:
        """Loads business_config.yaml and prompts.yaml into settings."""
        biz = load_yaml(CONFIG_DIR / "business_config.yaml")
        if biz:
            self.business = biz.get("business", {})
            self.services = biz.get("services", [])
            self.human_handoff = biz.get("human_handoff", {})
            self.barge_in = biz.get("barge_in", {})
            self.sms_config = biz.get("sms", {})
            self.privacy_config = biz.get("privacy", {})

        prompts_data = load_yaml(CONFIG_DIR / "prompts.yaml")
        if prompts_data:
            self.prompts = prompts_data


@lru_cache()
def get_settings() -> Settings:
    """Returns a cached singleton of Settings."""
    settings = Settings()
    settings.load_business_configs()
    return settings

from datetime import datetime
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://civicflow:civicflow@localhost:5433/civicflow"
    test_database_url: str = "postgresql+psycopg://civicflow:civicflow@localhost:5433/civicflow_test"

    anthropic_api_key: str = ""
    civicflow_llm_model: str = "claude-sonnet-5-5"
    agent_mode: str = "live"  # live | record | replay | rules
    agent_cache_dir: str = "agent_cache"

    time_scale: float = 60.0
    demo_mode: bool = True
    demo_epoch: datetime = datetime.fromisoformat("2026-11-05T09:00:00+05:30")

    secret_key: str = "change-me-in-real-life"
    media_root: str = "./media"
    media_url_ttl_s: int = 600
    oem_sim_api_key: str = "oem-sim-demo-key"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    scheduler_enabled: bool = True
    sensing_every_s: int = 60  # brief: every 2 min; faster for the demo

    @property
    def llm_enabled(self) -> bool:
        if self.agent_mode == "rules":
            return False
        if self.agent_mode == "replay":
            return True
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

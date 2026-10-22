from functools import lru_cache
from pathlib import Path

from hop_core.config import HopCoreSettings

# One .env at the repo root serves local runs (dev.sh) and docker compose, so
# there is no second copy to drift (hop-core AGENTS.md §3).
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class AuditSettings(HopCoreSettings):
    # Declared required by hop-core but unused here.
    redis_url: str = ""

    class Config(HopCoreSettings.Config):
        env_file = str(ENV_FILE)
        case_sensitive = False
        extra = "ignore"


@lru_cache
def get_settings() -> AuditSettings:
    return AuditSettings()

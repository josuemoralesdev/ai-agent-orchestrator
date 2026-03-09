from pydantic import BaseModel
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()


class Settings(BaseModel):
    env: str = os.getenv("ENV", "dev")
    audit_log_path: str = os.getenv("AUDIT_LOG_PATH", "logs/audit.ndjson")
    external_allowlist_domains: str = os.getenv("EXTERNAL_ALLOWLIST_DOMAINS", "httpbin.org")
    sqlite_db_path: str = "logs/state.db"
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "dev-admin-key")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    planner_model: str = os.getenv("PLANNER_MODEL", "gpt-4.1-mini")
    planner_kind: str = os.getenv("PLANNER_KIND", "rule")


settings = Settings()


def ensure_log_dir() -> None:
    Path(settings.audit_log_path).parent.mkdir(parents=True, exist_ok=True)


def allowlist_domains() -> set[str]:
    return {d.strip().lower() for d in settings.external_allowlist_domains.split(",") if d.strip()}


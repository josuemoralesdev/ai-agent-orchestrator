from pydantic import BaseModel
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()


class Settings(BaseModel):
    env: str = os.getenv("ENV", "dev")
    audit_log_path: str = os.getenv("AUDIT_LOG_PATH", "logs/audit.ndjson")


settings = Settings()


def ensure_log_dir() -> None:
    Path(settings.audit_log_path).parent.mkdir(parents=True, exist_ok=True)
from fastapi import Header, HTTPException
from src.core.config import settings


def require_admin(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="unauthorized")
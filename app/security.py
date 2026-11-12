import hmac
from fastapi import Header, HTTPException
from app.config import get_settings

async def require_engine_secret(x_engine_secret: str | None = Header(default=None)) -> None:
    expected = get_settings().engine_shared_secret
    if not expected or not x_engine_secret or not hmac.compare_digest(expected, x_engine_secret):
        raise HTTPException(status_code=401, detail="Authentification requise.")

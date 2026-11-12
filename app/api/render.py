from fastapi import APIRouter, Depends
from typing import Any
from app.security import require_engine_secret
from app.core.validator import validate_film
router = APIRouter(prefix="/render", dependencies=[Depends(require_engine_secret)])

@router.post("/validate")
async def validate(payload: dict[str, Any]):
    return validate_film(payload)

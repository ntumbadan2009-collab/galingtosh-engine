from fastapi import APIRouter, Depends, HTTPException
from app.config import get_settings
from app.security import require_engine_secret
from app.storage.supabase import SupabaseREST, SupabaseError

router = APIRouter(prefix="/tasks", dependencies=[Depends(require_engine_secret)])

@router.get("/{job_id}")
async def get_task(job_id: str):
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Le service Supabase n'est pas configuré.")
    try:
        async with SupabaseREST(settings.supabase_url, settings.supabase_service_role_key) as db:
            job = await db.get_render_job(job_id)
    except SupabaseError:
        raise HTTPException(status_code=502, detail="Impossible de consulter l'état de la tâche.") from None
    if job is None:
        raise HTTPException(status_code=404, detail="Tâche introuvable.")
    return {"job": job, "current_step": None}

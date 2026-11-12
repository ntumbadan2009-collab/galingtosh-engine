from fastapi import APIRouter, Depends, HTTPException, Request

from app.security import require_engine_secret
from app.storage.supabase import SupabaseError

router = APIRouter()


@router.post("/wake", dependencies=[Depends(require_engine_secret)])
async def wake_worker(request: Request):
    manager = getattr(request.app.state, "task_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Worker non configuré.")
    manager.wake()
    return {"accepted": True}


@router.get("/tasks/{job_id}", dependencies=[Depends(require_engine_secret)])
async def get_task(job_id: str, request: Request):
    db = getattr(request.app.state, "supabase", None)
    manager = getattr(request.app.state, "task_manager", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Stockage non configuré.")
    try:
        job = await db.get_render_job(job_id)
    except SupabaseError:
        raise HTTPException(status_code=404, detail="Tâche introuvable.") from None
    return {"job": job, "current_step": (manager.current.get("step") if manager and manager.current.get("job_id") == job_id else None)}

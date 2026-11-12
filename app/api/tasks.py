from fastapi import APIRouter, Depends, HTTPException
from app.security import require_engine_secret
from app.main_state import get_task_manager
router = APIRouter(dependencies=[Depends(require_engine_secret)])

@router.post("/wake")
async def wake(manager=Depends(get_task_manager)):
    manager.wake()
    return {"accepted": True}

@router.get("/tasks/{job_id}")
async def task_status(job_id: str, manager=Depends(get_task_manager)):
    try:
        job = await manager.db.get_render_job(job_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Tâche introuvable.") from None
    current = manager.current if manager.current and manager.current.get("id") == job_id else None
    return {"job": job, "current_step": manager.step if current else None}

from fastapi import Request, HTTPException

def get_task_manager(request: Request):
    manager = getattr(request.app.state, "task_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Worker non configuré.")
    return manager

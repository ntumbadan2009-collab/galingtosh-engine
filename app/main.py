from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.media import router as media_router
from app.api.render import router as render_router
from app.api.tasks import router as tasks_router
from app.config import get_settings
from app.core.task_manager import TaskManager
from app.storage.supabase import SupabaseREST


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    manager = None
    worker_task = None
    application.state.supabase = None
    application.state.task_manager = None

    if settings.supabase_service_role_key:
        db = SupabaseREST(settings.supabase_url, settings.supabase_service_role_key)
        manager = TaskManager(settings, db)
        application.state.supabase = db
        application.state.task_manager = manager
        worker_task = asyncio.create_task(manager.run(), name="galingtosh-worker")

    try:
        yield
    finally:
        if manager:
            await manager.shutdown()
        if worker_task:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task


app = FastAPI(title="Galingtosh Engine", version="0.2.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(media_router)
app.include_router(render_router)
app.include_router(tasks_router)

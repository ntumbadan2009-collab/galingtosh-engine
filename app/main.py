from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.render import router as render_router
from app.api.tasks import router as tasks_router
from app.config import get_settings
from app.storage.supabase import SupabaseREST
from app.core.task_manager import TaskManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    manager = None
    if settings.supabase_service_role_key and settings.engine_shared_secret:
        manager = TaskManager(settings, SupabaseREST(settings.supabase_url, settings.supabase_service_role_key))
        app.state.task_manager = manager
        manager.start()
    try:
        yield
    finally:
        if manager:
            await manager.stop()

app = FastAPI(title="Galingtosh Engine", version="0.2.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(render_router)
app.include_router(tasks_router)

from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.render import router as render_router
from app.api.tasks import router as tasks_router

app = FastAPI(title="Galingtosh Engine", version="0.2.0")
app.include_router(health_router)
app.include_router(render_router)
app.include_router(tasks_router)

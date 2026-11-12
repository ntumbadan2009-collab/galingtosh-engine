from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.render import router as render_router

app = FastAPI(title="Galingtosh Engine", version="0.1.0")
app.include_router(health_router)
app.include_router(render_router)

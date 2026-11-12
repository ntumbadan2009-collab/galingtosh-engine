from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from app.storage.supabase import SupabaseREST

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

class TaskManager:
    """Opérations métier d'une tâche; le moteur de rendu sera injecté dans l'étape pipeline."""
    def __init__(self, db: SupabaseREST):
        self.db = db

    async def claim(self, worker_id: str) -> dict[str, Any] | None:
        job = await self.db.claim_render_job(worker_id)
        if job:
            await self.db.patch_render_job(job["id"], {"progress": 0, "error": None})
        return job

    async def is_canceled(self, job_id: str) -> bool:
        job = await self.db.get_render_job(job_id)
        return job is None or job.get("status") == "canceled"

    async def progress(self, job_id: str, value: int) -> None:
        job = await self.db.get_render_job(job_id)
        if job is None or job.get("status") == "canceled":
            return
        previous = int(job.get("progress") or 0)
        await self.db.patch_render_job(job_id, {"progress": max(previous, min(99, value))})

    async def heartbeat(self, job_id: str) -> None:
        job = await self.db.get_render_job(job_id)
        if job is not None and job.get("status") == "running":
            # updated_at is maintained by the database trigger; PATCH only an allowed field.
            await self.db.patch_render_job(job_id, {"progress": int(job.get("progress") or 0)})

    async def succeed(self, job_id: str, output_path: str, warnings: list[str]) -> None:
        if not output_path or output_path.startswith("/") or ".." in output_path.split("/"):
            raise ValueError("Chemin de sortie invalide.")
        await self.db.patch_render_job(job_id, {
            "status": "done", "progress": 100, "output_path": output_path,
            "warnings": warnings, "error": None, "finished_at": utc_now()
        })

    async def fail(self, job_id: str, message: str) -> None:
        safe_message = " ".join(message.split())[:240] or "Le rendu a échoué."
        await self.db.patch_render_job(job_id, {
            "status": "failed", "error": safe_message, "finished_at": utc_now()
        })

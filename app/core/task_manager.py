from __future__ import annotations
import asyncio
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from app.config import Settings
from app.core.renderer import FilmRenderer
from app.media.supabase_resolver import resolve_film_media, write_credits
from app.storage.supabase import SupabaseREST

log = logging.getLogger("galingtosh.worker")

class TaskManager:
    def __init__(self, settings: Settings, db: SupabaseREST):
        self.settings, self.db = settings, db
        self.wake_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.current: dict | None = None
        self.step = "idle"
        self.loop_task: asyncio.Task | None = None

    def start(self) -> None:
        if self.loop_task is None:
            self.loop_task = asyncio.create_task(self.run_loop(), name="galingtosh-job-loop")

    async def stop(self) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.loop_task:
            self.loop_task.cancel()
            try:
                await self.loop_task
            except asyncio.CancelledError:
                pass

    def wake(self) -> None:
        self.wake_event.set()

    async def run_loop(self) -> None:
        await self.db.requeue_stale_render_jobs()
        next_requeue = asyncio.get_running_loop().time() + 300
        while not self.stop_event.is_set():
            try:
                if asyncio.get_running_loop().time() >= next_requeue:
                    await self.db.requeue_stale_render_jobs()
                    next_requeue = asyncio.get_running_loop().time() + 300
                job = await self.db.claim_render_job(self.settings.worker_id)
                if job:
                    self.current = {"id": job.get("id"), "status": "running"}
                    await self.process(job)
                    self.current = None
                    self.step = "idle"
                    continue
                self.wake_event.clear()
                try:
                    await asyncio.wait_for(self.wake_event.wait(), timeout=self.settings.poll_interval_seconds)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Worker loop failure (details intentionally hidden)")
                await asyncio.sleep(self.settings.poll_interval_seconds)

    async def _is_canceled(self, job_id: str) -> bool:
        state = await self.db.get_render_job(job_id)
        return state.get("status") in {"canceled", "failed"}

    async def process(self, job: dict) -> None:
        job_id = str(job["id"])
        Path(self.settings.temp_dir).mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="galingtosh-job-", dir=self.settings.temp_dir))
        output = work / "final.mp4"
        try:
            self.step = "lecture_film"
            await self.db.patch_render_job(job_id, {"progress": 2})
            film = await self.db.read_film(str(job["project_id"]), int(job["film_version"]))
            if await self._is_canceled(job_id): return
            self.step = "resolution_medias"
            media_files, warnings, credits = await resolve_film_media(
                film, str(job["project_id"]), str(job["user_id"]), self.db, work / "media")
            if await self._is_canceled(job_id): return
            self.step = "rendu_video"
            await self.db.patch_render_job(job_id, {"progress": 10, "warnings": warnings})
            render_task = asyncio.create_task(FilmRenderer(
                max_seconds=self.settings.max_render_seconds,
                max_output_mb=self.settings.max_output_mb).render(film, media_files, output))
            while not render_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(render_task), timeout=20)
                except asyncio.TimeoutError:
                    if await self._is_canceled(job_id):
                        render_task.cancel()
                        try: await render_task
                        except asyncio.CancelledError: pass
                        return
                    await self.db.patch_render_job(job_id, {"progress": 10})
            report = await render_task
            if await self._is_canceled(job_id): return
            self.step = "upload_rendu"
            warnings = list(dict.fromkeys(warnings + report["warnings"]))
            credits_path = work / f"{job_id}.credits.json"
            write_credits(credits_path, credits)
            object_path = f"{job['project_id']}/{job_id}.mp4"
            await self.db.upload_file("renders", object_path, output, "video/mp4")
            if credits:
                await self.db.upload_file("renders", f"{job['project_id']}/{job_id}.credits.json",
                                          credits_path, "application/json")
            if await self._is_canceled(job_id): return
            await self.db.patch_render_job(job_id, {"status": "done", "progress": 100,
                "output_path": object_path, "warnings": warnings,
                "finished_at": datetime.now(timezone.utc).isoformat()})
            self.step = "done"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Les détails internes ne sont jamais transmis à la base ni au client.
            log.warning("Render job failed (%s)", type(exc).__name__)
            try:
                state = await self.db.get_render_job(job_id)
                if state.get("status") not in {"canceled", "done"}:
                    await self.db.patch_render_job(job_id, {"status": "failed",
                        "error": "Le rendu a échoué. Vérifiez les médias et le Film JSON.",
                        "finished_at": datetime.now(timezone.utc).isoformat()})
            except Exception:
                log.error("Could not persist failed job state")
        finally:
            shutil.rmtree(work, ignore_errors=True)

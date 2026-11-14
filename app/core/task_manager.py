from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
import shutil
import socket
import tempfile
from pathlib import Path
from typing import Any

from app.config import Settings
from app.core.renderer import FilmRenderer, RenderError, _rss_mb
from app.media.supabase_resolver import resolve_film_media, write_credits
from app.media.subtitles import write_srt
from app.media.tts import synthesize_tts_tracks
from app.storage.supabase import SupabaseREST, SupabaseError

logger = logging.getLogger("galingtosh.worker")


class TaskManager:
    """Worker séquentiel : une seule tâche de rendu à la fois."""

    def __init__(self, settings: Settings, db: SupabaseREST):
        self.settings = settings
        self.db = db
        self.worker_id = settings.worker_id or socket.gethostname()
        self.wake_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.current: dict[str, str] = {}

    def wake(self) -> None:
        self.wake_event.set()

    async def run(self) -> None:
        try:
            await self.db.requeue_stale_render_jobs()
        except Exception:
            logger.exception("Échec du nettoyage initial Supabase.")
        last_requeue = asyncio.get_running_loop().time()
        while not self.stop_event.is_set():
            now = asyncio.get_running_loop().time()
            if now - last_requeue >= 300:
                try:
                    await self.db.requeue_stale_render_jobs()
                except Exception:
                    logger.exception("Échec du nettoyage périodique Supabase.")
                last_requeue = now
            try:
                job = await self.db.claim_render_job(self.worker_id)
                if job:
                    await self.process_job(job)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Échec du cycle de récupération des tâches Supabase.")
            self.wake_event.clear()
            try:
                await asyncio.wait_for(
                    self.wake_event.wait(), timeout=self.settings.poll_interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def shutdown(self) -> None:
        self.stop_event.set()
        self.wake_event.set()

    async def _is_canceled(self, job_id: str) -> bool:
        job = await self.db.get_render_job(job_id)
        return job.get("status") != "running"

    async def _render_with_heartbeat(
        self, job_id: str, renderer: FilmRenderer, film: dict,
        media_files: dict[str, Path], output: Path,
    ) -> dict[str, Any] | None:
        last_progress = 15
        async def on_progress(value: int, stage: str) -> None:
            nonlocal last_progress
            value = max(last_progress, min(89, int(value)))
            if value != last_progress:
                await self.db.patch_render_job(job_id, {"progress": value, "updated_at": datetime.now(timezone.utc).isoformat()})
                last_progress = value
            logger.info("Render job=%s stage=%s progress=%s rss_tree_mb=%s", job_id, stage, value, _rss_mb())
        render_task = asyncio.create_task(renderer.render(film, media_files, output, on_progress))
        try:
            while not render_task.done():
                await asyncio.sleep(25)
                job = await self.db.get_render_job(job_id)
                if job.get("status") == "canceled":
                    render_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await render_task
                    return None
                if job.get("status") != "running":
                    render_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await render_task
                    raise RenderError("La tâche n'est plus active.")
                await self.db.patch_render_job(job_id, {"progress": last_progress, "updated_at": datetime.now(timezone.utc).isoformat()})
                logger.info("Render heartbeat job=%s progress=%s rss_tree_mb=%s", job_id, last_progress, _rss_mb())
            return await render_task
        except asyncio.CancelledError:
            render_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await render_task
            raise

    async def process_job(self, claimed: dict) -> None:
        job_id = str(claimed.get("id") or "")
        if not job_id:
            logger.error("Une tâche réclamée ne contient pas d'identifiant.")
            return
        self.current = {"job_id": job_id, "step": "initialisation"}
        Path(self.settings.temp_dir).mkdir(parents=True, exist_ok=True)
        workdir = Path(tempfile.mkdtemp(prefix="galingtosh-job-", dir=self.settings.temp_dir))
        output = workdir / "final.mp4"
        try:
            job = await self.db.get_render_job(job_id)
            if job.get("status") != "running":
                return
            await self.db.patch_render_job(job_id, {"progress": 0})
            self.current["step"] = "lecture du Film JSON"
            film = await self.db.read_film(job["project_id"], int(job["film_version"]))
            if await self._is_canceled(job_id):
                return

            self.current["step"] = "résolution des médias"
            media_files, media_warnings, credits = await resolve_film_media(
                film, str(job["project_id"]), str(job["user_id"]), self.db, workdir
            )
            if await self._is_canceled(job_id):
                return
            tts_files, tts_warnings = await synthesize_tts_tracks(film, workdir)
            media_files.update(tts_files)
            media_warnings.extend(tts_warnings)
            if await self._is_canceled(job_id):
                return
            await self.db.patch_render_job(job_id, {"progress": 15, "updated_at": datetime.now(timezone.utc).isoformat()})

            self.current["step"] = "rendu vidéo"
            renderer = FilmRenderer(
                max_seconds=self.settings.max_render_seconds,
                max_output_mb=self.settings.max_output_mb,
            )
            result = await self._render_with_heartbeat(
                job_id, renderer, film, media_files, output
            )
            if result is None or await self._is_canceled(job_id):
                return

            warnings = list(dict.fromkeys(media_warnings + result.get("warnings", [])))
            self.current["step"] = "préparation des crédits"
            credits_path = workdir / f"{job_id}.credits.json"
            if credits:
                write_credits(credits_path, credits)
            srt_path = workdir / f"{job_id}.srt"
            has_srt = write_srt(film.get("subtitles", []) or [], srt_path,
                                (film.get("info") or {}).get("language"))

            project_id = str(job["project_id"])
            output_object = f"{project_id}/{job_id}.mp4"
            self.current["step"] = "envoi du rendu"
            if await self._is_canceled(job_id):
                return
            await self.db.patch_render_job(job_id, {"progress": 90})
            await self.db.upload_file(
                "renders", output_object, output, "video/mp4"
            )
            if credits:
                # Vérifier de nouveau juste avant chaque écriture Storage :
                # une annulation peut survenir pendant l'envoi de la vidéo.
                if await self._is_canceled(job_id):
                    return
                await self.db.upload_file(
                    "renders", f"{project_id}/{job_id}.credits.json",
                    credits_path, "application/json",
                )
            if has_srt:
                if await self._is_canceled(job_id):
                    return
                await self.db.upload_file(
                    "renders", f"{project_id}/{job_id}.srt", srt_path, "application/x-subrip"
                )
            if await self._is_canceled(job_id):
                return
            await self.db.patch_render_job(job_id, {
                "status": "done",
                "progress": 100,
                "output_path": output_object,
                "warnings": warnings,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
            self.current["step"] = "terminé"
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                job = await self.db.get_render_job(job_id)
                if job.get("status") == "running":
                    await self.db.patch_render_job(job_id, {"status": "queued", "progress": 0})
            raise
        except Exception:
            logger.exception("Échec de la tâche de rendu %s.", job_id)
            with contextlib.suppress(Exception):
                job = await self.db.get_render_job(job_id)
                if job.get("status") == "running":
                    await self.db.patch_render_job(job_id, {
                        "status": "failed",
                        "error": "Le rendu a échoué. Vérifiez le Film JSON et les médias, puis réessayez.",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    })
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            self.current = {}

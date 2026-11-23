from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
import shutil
import socket
import tempfile
import uuid
from pathlib import Path
from typing import Any

from app.config import Settings
from app.core.renderer import FilmRenderer, RenderError, _rss_mb
from app.core.checkpoints import SceneCheckpoints
from app.core.narration import align_scene_narrations
from app.media.supabase_resolver import resolve_film_media, write_credits
from app.media.subtitles import write_srt
from app.media.tts import synthesize_scene_narrations, synthesize_tts_tracks
from app.media.procedural import synthesize_effect
from app.storage.supabase import SupabaseREST, SupabaseError

logger = logging.getLogger("galingtosh.worker")


class TaskManager:
    """Worker séquentiel : une seule tâche de rendu à la fois."""

    def __init__(self, settings: Settings, db: SupabaseREST):
        self.settings = settings
        self.db = db
        self.worker_id = f"{settings.worker_id or socket.gethostname()}-{uuid.uuid4().hex[:12]}"
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
                # Durable production planning uses the same sequential worker.
                # Prioritize queued renders; a tick performs a single tool call.
                result = await self.db.run_production_tick()
                if result == "advanced":
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
        return job.get("status") != "running" or job.get("worker_id") != self.worker_id

    async def _render_with_heartbeat(
        self, job_id: str, renderer: FilmRenderer, film: dict,
        media_files: dict[str, Path], output: Path, checkpoints: SceneCheckpoints,
    ) -> dict[str, Any] | None:
        last_progress = 15
        async def on_progress(value: int, stage: str) -> None:
            nonlocal last_progress
            value = max(last_progress, min(89, int(value)))
            if value != last_progress:
                await self._patch(job_id, {"progress": value, "updated_at": datetime.now(timezone.utc).isoformat()})
                last_progress = value
            logger.info("Render job=%s stage=%s progress=%s rss_tree_mb=%s", job_id, stage, value, _rss_mb())
        return await renderer.render(film, media_files, output, on_progress, checkpoints=checkpoints)

    async def _patch(self, job_id: str, fields: dict) -> None:
        fields = {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
        await self.db.patch_render_job(job_id, fields, worker_id=self.worker_id)

    async def process_job(self, claimed: dict) -> None:
        """Keep the lease alive during downloads, TTS, encoding AND upload."""
        task = asyncio.create_task(self._process_job(claimed))
        deadline = asyncio.get_running_loop().time() + max(900, self.settings.max_render_seconds * 6)
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=20)
                if done:
                    break
                if await self._is_canceled(str(claimed["id"])):
                    task.cancel()
                    return
                if asyncio.get_running_loop().time() >= deadline:
                    await self._patch(str(claimed["id"]), {"status": "failed", "error": "Temps maximal de production dépassé.", "finished_at": datetime.now(timezone.utc).isoformat()})
                    task.cancel()
                    return
                await self._patch(str(claimed["id"]), {})
            await task
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _process_job(self, claimed: dict) -> None:
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
            if job.get("status") != "running" or job.get("worker_id") != self.worker_id:
                return
            await self._patch(job_id, {"progress": 0})
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
            if tts_warnings:
                raise RenderError(" ".join(tts_warnings))
            scene_tts_files, scene_tts_durations, scene_tts_warnings = await synthesize_scene_narrations(film, workdir)
            media_files.update(scene_tts_files)
            media_warnings.extend(scene_tts_warnings)
            if scene_tts_warnings:
                raise RenderError(" ".join(scene_tts_warnings))
            # A scene with its own narration takes its actual spoken length as
            # its final duration. Scale visual shot boundaries with that scene;
            # never time-stretch, clip, or let its narration spill into the next one.
            narration_tracks, narration_alignment_warnings = align_scene_narrations(film, scene_tts_durations)
            media_warnings.extend(narration_alignment_warnings)
            (film.setdefault("audio", {})).setdefault("tracks", []).extend(narration_tracks)
            # SFX are synthesized locally in Python only. Never mix a downloaded
            # or imported sound effect into a render while procedural audio is active.
            audio_tracks = (film.get("audio") or {}).get("tracks", [])
            for track in audio_tracks:
                if not isinstance(track, dict): continue
                if track.get("kind") == "music":
                    if track.get("mediaRef"):
                        track["disabled"] = True
                        media_warnings.append("Piste musicale importée ignorée : seule la musique procédurale par scène est utilisée.")
                    continue
                if track.get("kind") != "sfx": continue
                expected = str(track.get("expectedContent") or "").strip()
                fallback = workdir / f"generated_sfx_{track.get('id','sound')}.wav"
                duration = max((float(e.get("durationSec",2)) for e in track.get("events",[]) if isinstance(e,dict)),default=2.0)
                generated = await asyncio.to_thread(synthesize_effect, expected, fallback, min(12,max(.25,duration))) if expected else False
                if generated:
                    ref = f"__sfx_{track.get('id')}"
                    media_files[ref] = fallback
                    track["mediaRef"] = ref
                    media_warnings.append(f"Effet « {expected} » synthétisé par Python selon le motif procédural pris en charge.")
                else:
                    track["disabled"] = True
                    track.pop("mediaRef", None)
                    media_warnings.append(f"Effet « {expected or 'non décrit'} » omis : ce type de son n’est pas encore pris en charge par la synthèse procédurale.")
            referenced = {shot.get("mediaRef") for scene in film.get("scenes", []) for shot in scene.get("shots", []) if shot.get("mediaRef")}
            referenced.update(track.get("mediaRef") for track in audio_tracks if track.get("mediaRef") and not track.get("disabled"))
            if referenced - media_files.keys():
                raise RenderError("Médias indisponibles : " + ", ".join(sorted(referenced - media_files.keys())))
            if await self._is_canceled(job_id):
                return
            await self._patch(job_id, {"progress": 15, "updated_at": datetime.now(timezone.utc).isoformat()})

            self.current["step"] = "rendu vidéo"
            renderer = FilmRenderer(
                max_seconds=self.settings.max_render_seconds,
                max_output_mb=self.settings.max_output_mb,
            )
            # Durable artifacts are scoped to the authenticated job owner,
            # project and job ID. They survive worker restarts and /tmp loss.
            checkpoints = SceneCheckpoints(
                self.db, str(job["user_id"]), str(job["project_id"]), job_id
            )
            result = await self._render_with_heartbeat(
                job_id, renderer, film, media_files, output, checkpoints
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
            await self._patch(job_id, {"progress": 90})
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
            await self._patch(job_id, {
                "status": "done",
                "progress": 100,
                "output_path": output_object,
                "warnings": warnings,
                "technical_report": {k: v for k, v in result.items() if k != "output"},
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
            self.current["step"] = "terminé"
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                job = await self.db.get_render_job(job_id)
                if job.get("status") == "running" and job.get("worker_id") == self.worker_id:
                    await self._patch(job_id, {"status": "queued", "progress": 0})
            raise
        except Exception as exc:
            logger.exception("Échec de la tâche de rendu %s.", job_id)
            with contextlib.suppress(Exception):
                job = await self.db.get_render_job(job_id)
                if job.get("status") == "running" and job.get("worker_id") == self.worker_id:
                    await self._patch(job_id, {
                        "status": "failed",
                        "error": str(exc)[:500] if isinstance(exc, RenderError) else "Le rendu a échoué pendant : " + self.current.get("step", "production") + ". Réessayez ou vérifiez les médias.",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    })
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            self.current = {}


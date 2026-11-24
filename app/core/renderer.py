from __future__ import annotations

import shutil
import tempfile
import logging
import gc
from app.core.checkpoints import SceneCheckpoints, fingerprint
from pathlib import Path
from typing import Any, Callable, Awaitable

from app.core.validator import validate_film
from app.core.editorial import level3, timeline_issues, inspect_render
from app.core.narrative_policy import narrative_issues
from app.media.narrative_cards import render_code_card
from app.media.motion_graphics import render_motion_graphic
from app.media.ffmpeg import FFmpegError, probe_media, run_ffmpeg
from app.media.images import normalize_image
from app.media.video import normalize_video
from app.media.transitions import assemble_segments
from app.media.audio import mix_audio
from app.media.compression import fit_mp4_to_limit
from app.media.procedural import compose_bed
from app.media.subtitles import write_srt
from app.media.effects import build_video_filters, finish_video

logger = logging.getLogger("galingtosh.renderer")

def _rss_mb() -> float | None:
    """RSS cumulé du worker et de ses descendants (notamment FFmpeg)."""
    try:
        proc_root = Path("/proc")
        ppid_by_pid = {}
        rss_by_pid = {}
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / "stat").read_text(encoding="ascii")
                fields = stat[stat.rfind(")") + 2:].split()
                ppid_by_pid[int(entry.name)] = int(fields[1])
                for line in (entry / "status").read_text(encoding="ascii").splitlines():
                    if line.startswith("VmRSS:"):
                        rss_by_pid[int(entry.name)] = int(line.split()[1])
                        break
            except (OSError, ValueError, IndexError):
                continue
        root = __import__("os").getpid()
        descendants = {root}
        changed = True
        while changed:
            changed = False
            for pid, parent in ppid_by_pid.items():
                if parent in descendants and pid not in descendants:
                    descendants.add(pid)
                    changed = True
        return round(sum(rss_by_pid.get(pid, 0) for pid in descendants) / 1024, 1)
    except (OSError, ValueError):
        return None

def _memory(stage: str) -> None:
    rss = _rss_mb()
    logger.info("MEM stage=%s rss_mb=%s", stage, rss if rss is not None else "unavailable")

ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:3": (4, 3), "4:5": (4, 5), "21:9": (21, 9)}

class RenderError(RuntimeError):
    pass

def output_size(film: dict[str, Any]) -> tuple[int, int]:
    fmt = film.get("format") or {}
    aspect = fmt.get("aspect", "16:9")
    if aspect == "custom":
        w, h = int(fmt.get("width", 1280)), int(fmt.get("height", 720))
        scale = min(1.0, 1920 / max(w, h))
        w, h = int(w * scale), int(h * scale)
    else:
        aw, ah = ASPECTS.get(aspect, (16, 9))
        resolution = (film.get("render") or {}).get("resolution", "720p")
        short = {"720p": 720, "1080p": 1080, "4k": 2160}.get(resolution, 720)
        if aw >= ah: h, w = short, round(short * aw / ah)
        else: w, h = short, round(short * ah / aw)
    return max(2, w - w % 2), max(2, h - h % 2)

def collect_media(film: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["id"]: m for m in film.get("media", []) if isinstance(m, dict) and isinstance(m.get("id"), str)}

class FilmRenderer:
    """Montage audiovisuel déterministe ; aucun média image/vidéo n'est généré par IA."""
    def __init__(self, *, max_seconds: int = 600, max_output_mb: int = 45):
        self.max_seconds = max_seconds
        self.max_output_mb = max_output_mb

    async def render(self, film: dict[str, Any], media_files: dict[str, Path], output: Path, progress_callback: Callable[[int, str], Awaitable[None]] | None = None, checkpoints: SceneCheckpoints | None = None) -> dict[str, Any]:
        report = validate_film(film)
        if (film.get("info") or {}).get("visualPolicy") == "strict":
            issues = narrative_issues(film)
            if issues:
                raise RenderError("Montage non conforme aux preuves visuelles : " + " ".join(issues[:5]))
        if not report["valid"]:
            raise RenderError("Film JSON invalide : " + " ".join(report["errors"][:4]))
        editorial = level3(film)
        if editorial:
            problems = timeline_issues(film)
            if problems:
                raise RenderError("Contrôle éditorial : " + " ".join(problems[:5]))
        scenes = sorted(film.get("scenes", []), key=lambda x: x.get("order", 0))
        total_duration = sum(float(s.get("durationSec", 0)) for s in scenes)
        if total_duration <= 0: raise RenderError("La durée totale du film doit être positive.")
        if total_duration > self.max_seconds: raise RenderError(f"Durée demandée supérieure à la limite de {self.max_seconds} secondes.")
        width, height = output_size(film)
        if width * height > 1920 * 1080:
            raise RenderError("Résolution trop élevée pour le profil mémoire du moteur : maximum 1920 × 1080 pixels.")
        fps = int(min(30, max(1, (film.get("format") or {}).get("fps", 24))))
        media_index = collect_media(film)
        warnings = list(report["warnings"])
        output.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="gt-render-"))
        segments: list[Path] = []
        segment_shot_ids: list[str | None] = []
        segment_durations: list[float] = []
        # Includes final narration alignment and all render settings. Altered
        # scenes, durations or film versions cannot reuse stale segment files.
        render_signature = fingerprint({"format": 1, "film": film, "resolution": [width, height], "fps": fps})
        try:
            _memory("render_start")
            total_shots = max(1, sum(len(s.get("shots", [])) for s in scenes))
            completed_shots = 0
            for scene_index, scene in enumerate(scenes):
                _memory(f"scene_{scene_index+1}_start")
                scene_signature = fingerprint({"render": render_signature, "scene": scene_index})
                scene_duration = float(scene.get("durationSec", 0))
                shots = sorted(scene.get("shots", []), key=lambda x: x.get("order", 0))
                # Some agent plans express each shot's intended length in
                # outSec while leaving every inSec at zero. Interpret those
                # as consecutive durations; otherwise the second shot becomes
                # a one-second sliver after overlap correction.
                if len(shots) > 1 and all(abs(float(s.get("inSec", 0) or 0)) < 0.02 for s in shots):
                    cursor_for_shots = 0.0
                    for shot in shots:
                        intended = max(0.05, float(shot.get("outSec", 0) or 0) - float(shot.get("inSec", 0) or 0))
                        shot["inSec"] = round(cursor_for_shots, 3)
                        shot["outSec"] = round(min(scene_duration, cursor_for_shots + intended), 3)
                        cursor_for_shots = float(shot["outSec"])
                if checkpoints is not None:
                    previous = await checkpoints.restore(scene_index, scene_signature, work)
                    if previous:
                        for part in previous:
                            segments.append(work / part["name"])
                            segment_shot_ids.append(part.get("shot_id"))
                            segment_durations.append(float(part["duration"]))
                        completed_shots += len(scene.get("shots", []))
                        if progress_callback:
                            await progress_callback(min(78, 18 + int(60 * completed_shots / total_shots)),
                                                    f"scène {scene_index + 1} restaurée")
                        continue
                cursor = 0.0
                scene_segment_start = len(segments)
                for shot_index, shot in enumerate(shots):
                    start = max(0.0, float(shot.get("inSec", 0)))
                    end = min(scene_duration, float(shot.get("outSec", 0)))
                    if start < cursor:
                        warnings.append(f"Scène {scene_index+1} : chevauchement de plans, le plan suivant est décalé.")
                        start = cursor
                    if end <= start: continue
                    if start > cursor + 0.02:
                        # Close timeline gaps by extending the preceding shot.
                        # Intentional black is not inferred from missing timing.
                        warnings.append(f"Scène {scene_index+1} : intervalle vide comblé par le dernier plan.")
                        if len(segments) > scene_segment_start:
                            previous = segments[-1]
                            extended = work / f"segment_{len(segments):04d}_hold.mp4"
                            gap = min(scene_duration - cursor, start - cursor)
                            if gap > 0:
                                await run_ffmpeg(["-i", str(previous), "-vf", f"tpad=stop_mode=clone:stop_duration={gap:.4f}",
                                    "-t", f"{segment_durations[-1]+gap:.4f}", "-an", "-c:v", "libx264", "-preset", "ultrafast",
                                    "-threads", "1", "-pix_fmt", "yuv420p", str(extended)])
                                previous.unlink(missing_ok=True)
                                segments[-1] = extended
                                segment_durations[-1] += gap
                                cursor += gap
                        else:
                            start = cursor
                    duration = end - start
                    media_id = shot.get("mediaRef")
                    media = media_index.get(media_id) if media_id else None
                    source = media_files.get(media_id) if media_id else None
                    if media and media.get("kind") == "model3d":
                        warnings.append("Média 3D ignoré : format non pris en charge."); source = None
                    segment = work / f"segment_{len(segments):04d}.mp4"
                    if shot.get("visualMode") == "programmatic":
                        if shot.get("visualSpec"):
                            # Level 2: drawings are generated from narrated,
                            # audited fragments; no external images/videos.
                            await render_motion_graphic(
                                segment, spec=shot["visualSpec"],
                                scene_title=str(scene.get("title") or ""),
                                scene_number=scene_index + 1,
                                width=width, height=height, fps=fps,
                                duration=duration, workdir=work,
                            )
                        else:
                            # V1 legacy remains stable for existing projects.
                            card = work / f"narrative_card_{scene_index:03d}_{shot_index:03d}.png"
                            render_code_card(
                                card, narration_quote=str(shot["visualText"]),
                                scene_title=str(scene.get("title") or ""),
                                scene_number=scene_index + 1,
                                width=width, height=height,
                                style=str(shot.get("cardStyle") or "focus"),
                            )
                            camera = ((shot.get("camera") or {}).get("type") or "ken_burns")
                            await normalize_image(card, segment, width, height, fps, duration,
                                                  "ken_burns" if camera == "none" else camera)
                    elif not source or not source.is_file():
                        if (film.get("info") or {}).get("visualPolicy") == "strict":
                            raise RenderError(
                                f"Média visuel du plan {scene_index+1}.{shot_index+1} devenu "
                                "indisponible : refus d'insérer un fond noir qui tromperait la narration."
                            )
                        warnings.append(f"Plan {shot.get('id', shot_index+1)} : média absent, fond noir utilisé.")
                        await self._black(segment, width, height, fps, duration)
                    else:
                        kind = (media or {}).get("kind")
                        if source.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                            adjustment = await normalize_video(source, segment, width, height, fps, float(shot.get("sourceInSec", 0) or 0), duration, ((shot.get("camera") or {}).get("type") or "none"))
                            if adjustment: warnings.append(f"Plan {shot.get('id', shot_index+1)} : {adjustment}")
                        elif kind in {"image", "svg", "chart"} or source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                            camera = ((shot.get("camera") or {}).get("type") or "none")
                            await normalize_image(source, segment, width, height, fps, duration, camera)
                        elif kind == "video" or source.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                            adjustment = await normalize_video(source, segment, width, height, fps, float(shot.get("sourceInSec", 0)), duration, ((shot.get("camera") or {}).get("type") or "none"))
                            if adjustment: warnings.append(f"Plan {shot.get('id', shot_index+1)} : {adjustment}")
                        else:
                            warnings.append(f"Type de média non visuel pour le plan {shot_index+1}.")
                            await self._black(segment, width, height, fps, duration)
                    segments.append(segment)
                    segment_shot_ids.append(str(shot.get("id")) if shot.get("id") is not None else None)
                    segment_durations.append(duration); cursor = end
                    completed_shots += 1
                    _memory(f"scene_{scene_index+1}_shot_{shot_index+1}_done")
                    if progress_callback:
                        await progress_callback(min(78, 18 + int(60 * completed_shots / total_shots)), f"plan {completed_shots}/{total_shots}")
                if cursor < scene_duration:
                    if len(segments) > scene_segment_start and segment_shot_ids[-1] is not None:
                        warnings.append(f"Scène {scene_index+1} : fin non couverte, dernier plan prolongé.")
                        previous = segments[-1]
                        remaining = scene_duration - cursor
                        extended = work / f"segment_{len(segments):04d}_hold.mp4"
                        await run_ffmpeg(["-i", str(previous), "-vf", f"tpad=stop_mode=clone:stop_duration={remaining:.4f}",
                            "-t", f"{segment_durations[-1]+remaining:.4f}", "-an", "-c:v", "libx264", "-preset", "ultrafast",
                            "-threads", "1", "-pix_fmt", "yuv420p", str(extended)])
                        previous.unlink(missing_ok=True)
                        segments[-1] = extended
                        segment_durations[-1] += remaining
                    else:
                        warnings.append(f"Scène {scene_index+1} : aucun plan exploitable pour couvrir la fin.")
                        black = work / f"segment_{len(segments):04d}.mp4"
                        await self._black(black, width, height, fps, scene_duration-cursor)
                        segments.append(black); segment_shot_ids.append(None); segment_durations.append(scene_duration-cursor)
                if checkpoints is not None and len(segments) > scene_segment_start:
                    completed_scene = [
                        {"name": path.name, "shot_id": shot_id, "duration": duration}
                        for path, shot_id, duration in zip(
                            segments[scene_segment_start:],
                            segment_shot_ids[scene_segment_start:],
                            segment_durations[scene_segment_start:],
                        )
                    ]
                    await checkpoints.save(scene_index, scene_signature, completed_scene, work)
                gc.collect()
                _memory(f"scene_{scene_index+1}_complete")
            if not segments: raise RenderError("Aucun plan exploitable dans le Film JSON.")
            assembled = work / "assembled.mp4"
            _memory("before_incremental_assembly")
            warnings.extend(await assemble_segments(segments, segment_shot_ids, segment_durations,
                film.get("transitions", []) or [], assembled, fps, self.max_seconds))
            _memory("after_incremental_assembly")
            if progress_callback: await progress_callback(82, "assemblage terminé")
            targets = {}
            offset = 0.0
            for scene in scenes:
                length = float(scene.get("durationSec", 0))
                targets[str(scene.get("id"))] = (offset, offset+length)
                for shot in scene.get("shots", []):
                    targets[str(shot.get("id"))] = (offset+float(shot.get("inSec",0)), offset+min(length,float(shot.get("outSec",length))))
                offset += length
            filters, effect_warnings = build_video_filters(film.get("effects", []) or [], total_duration, width, height, targets, text_directory=work)
            warnings.extend(effect_warnings)
            applied_effect_count = len(filters)
            subtitle_path = work / "captions.srt"
            has_subtitles = write_srt(film.get("subtitles", []) or [], subtitle_path, (film.get("info") or {}).get("language"))
            styled = work / "styled.mp4"
            _memory("before_effects_subtitles")
            await finish_video(assembled, styled, filters, subtitle_path if has_subtitles else None)
            _memory("after_effects_subtitles")
            if progress_callback: await progress_callback(86, "effets et sous-titres terminés")
            audio = film.get("audio") or {}
            tracks = list(audio.get("tracks") or [])
            music = audio.get("proceduralMusic") or {}
            if music.get("enabled") and compose_bed(scenes, music.get("cues") or [], work / "procedural.wav"):
                media_files = {**media_files, "__procedural_music": work / "procedural.wav"}
                tracks.append({"id":"__procedural_music", "kind":"music", "mediaRef":"__procedural_music",
                               # Earlier plans stored -15 dB, which made this
                               # small procedural pad effectively inaudible on
                               # phone speakers. Keep it below narration but
                               # enforce a modest audible floor.
                               "volumeDb":max(-8.0, min(0.0, float(music.get("volumeDb", -8))))})
            has_audio, audio_warnings = await mix_audio(styled, tracks, media_files, output,
                total_duration, (film.get("render") or {}).get("audioBitrateKbps", 128), editorial=editorial)
            warnings.extend(audio_warnings)
            _memory("after_audio_mix")
            if progress_callback: await progress_callback(89, "mixage audio terminé")
            if not has_audio: styled.replace(output)
            compression = await fit_mp4_to_limit(
                output, self.max_output_mb,
                audio_bitrate_kbps=int((film.get("render") or {}).get("audioBitrateKbps", 128)),
            )
            if compression.get("recompressed"):
                warnings.append(
                    "Fichier volumineux : compression H.264 finale appliquée sans retirer de scènes "
                    "ni de narration pour respecter la limite d'envoi."
                )
            size_mb = output.stat().st_size / (1024 * 1024)
            _memory("before_final_probe")
            probe = await probe_media(str(output))
            qa = None
            if editorial:
                if progress_callback: await progress_callback(94, "contrôle audiovisuel du fichier final")
                expected = [s for s in scenes if (s.get("narration") or {}).get("text")]
                voices = []
                for scene in expected:
                    ref = "__scene_narration_" + str(scene.get("id", ""))
                    voice = media_files.get(ref)
                    if not voice or not voice.is_file():
                        raise RenderError("Contrôle qualité : voix de scène manquante.")
                    voices.append(voice)
                qa = await inspect_render(output, probe, total_duration, bool(expected), voices, fps)
                if not qa["passed"]:
                    raise RenderError("Contrôle qualité : " + " ".join(qa["issues"]))
            _memory("render_complete")
            streams = probe.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), {})
            return {"output": str(output), "duration_seconds": float(probe.get("format", {}).get("duration", 0)),
                "width": video.get("width"), "height": video.get("height"), "fps": fps,
                "size_mb": round(size_mb, 3), "compression": compression, "warnings": list(dict.fromkeys(warnings)),
                "audio": any(s.get("codec_type") == "audio" for s in streams),
                "subtitles_burned": has_subtitles, "effects_applied": applied_effect_count, "editorial_quality": qa}
        except (OSError, FFmpegError) as exc:
            raise RenderError(str(exc)) from None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    async def _black(self, destination: Path, width: int, height: int, fps: int, duration: float):
        await run_ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}",
            "-t", str(duration), "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-threads", "1", "-pix_fmt", "yuv420p", str(destination)])


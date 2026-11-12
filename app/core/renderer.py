from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.core.validator import validate_film
from app.media.ffmpeg import FFmpegError, probe_media, run_ffmpeg
from app.media.images import normalize_image
from app.media.video import normalize_video
from app.media.transitions import assemble_segments
from app.media.audio import mix_audio
from app.media.subtitles import write_srt
from app.media.effects import build_video_filters, finish_video

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

    async def render(self, film: dict[str, Any], media_files: dict[str, Path], output: Path) -> dict[str, Any]:
        report = validate_film(film)
        if not report["valid"]:
            raise RenderError("Film JSON invalide : " + " ".join(report["errors"][:4]))
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
        try:
            for scene_index, scene in enumerate(scenes):
                scene_duration = float(scene.get("durationSec", 0))
                shots = sorted(scene.get("shots", []), key=lambda x: x.get("order", 0))
                cursor = 0.0
                for shot_index, shot in enumerate(shots):
                    start = max(0.0, float(shot.get("inSec", 0)))
                    end = min(scene_duration, float(shot.get("outSec", 0)))
                    if start < cursor:
                        warnings.append(f"Scène {scene_index+1} : chevauchement de plans, le plan suivant est décalé.")
                        start = cursor
                    if end <= start: continue
                    if start > cursor + 0.02:
                        warnings.append(f"Scène {scene_index+1} : intervalle vide rendu en noir.")
                        black = work / f"segment_{len(segments):04d}.mp4"
                        await self._black(black, width, height, fps, start-cursor)
                        segments.append(black); segment_shot_ids.append(None); segment_durations.append(start-cursor)
                    duration = end - start
                    media_id = shot.get("mediaRef")
                    media = media_index.get(media_id) if media_id else None
                    source = media_files.get(media_id) if media_id else None
                    if media and media.get("kind") == "model3d":
                        warnings.append("Média 3D ignoré : format non pris en charge."); source = None
                    segment = work / f"segment_{len(segments):04d}.mp4"
                    if not source or not source.is_file():
                        warnings.append(f"Plan {shot.get('id', shot_index+1)} : média absent, fond noir utilisé.")
                        await self._black(segment, width, height, fps, duration)
                    else:
                        kind = (media or {}).get("kind")
                        if kind in {"image", "svg", "chart"} or source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                            camera = ((shot.get("camera") or {}).get("type") or "none")
                            await normalize_image(source, segment, width, height, fps, duration, camera)
                        elif kind == "video" or source.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                            await normalize_video(source, segment, width, height, fps, start, duration, ((shot.get("camera") or {}).get("type") or "none"))
                        else:
                            warnings.append(f"Type de média non visuel pour le plan {shot_index+1}.")
                            await self._black(segment, width, height, fps, duration)
                    segments.append(segment)
                    segment_shot_ids.append(str(shot.get("id")) if shot.get("id") is not None else None)
                    segment_durations.append(duration); cursor = end
                if cursor < scene_duration:
                    warnings.append(f"Scène {scene_index+1} : fin non couverte, fond noir ajouté.")
                    black = work / f"segment_{len(segments):04d}.mp4"
                    await self._black(black, width, height, fps, scene_duration-cursor)
                    segments.append(black); segment_shot_ids.append(None); segment_durations.append(scene_duration-cursor)
            if not segments: raise RenderError("Aucun plan exploitable dans le Film JSON.")
            assembled = work / "assembled.mp4"
            warnings.extend(await assemble_segments(segments, segment_shot_ids, segment_durations,
                film.get("transitions", []) or [], assembled, fps, self.max_seconds))
            filters, effect_warnings = build_video_filters(film.get("effects", []) or [], total_duration, width, height)
            warnings.extend(effect_warnings)
            applied_effect_count = len(filters)
            subtitle_path = work / "captions.srt"
            has_subtitles = write_srt(film.get("subtitles", []) or [], subtitle_path, (film.get("info") or {}).get("language"))
            styled = work / "styled.mp4"
            await finish_video(assembled, styled, filters, subtitle_path if has_subtitles else None)
            audio = film.get("audio") or {}
            has_audio, audio_warnings = await mix_audio(styled, audio.get("tracks") or [], media_files, output,
                total_duration, (film.get("render") or {}).get("audioBitrateKbps", 128))
            warnings.extend(audio_warnings)
            if not has_audio: styled.replace(output)
            size_mb = output.stat().st_size / (1024 * 1024)
            if size_mb > self.max_output_mb:
                output.unlink(missing_ok=True)
                raise RenderError(f"Fichier final supérieur à la limite de {self.max_output_mb} Mo.")
            probe = await probe_media(str(output))
            streams = probe.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), {})
            return {"output": str(output), "duration_seconds": float(probe.get("format", {}).get("duration", 0)),
                "width": video.get("width"), "height": video.get("height"), "fps": fps,
                "size_mb": round(size_mb, 3), "warnings": list(dict.fromkeys(warnings)),
                "audio": any(s.get("codec_type") == "audio" for s in streams),
                "subtitles_burned": has_subtitles, "effects_applied": applied_effect_count}
        except (OSError, FFmpegError) as exc:
            raise RenderError(str(exc)) from None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    async def _black(self, destination: Path, width: int, height: int, fps: int, duration: float):
        await run_ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}",
            "-t", str(duration), "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-threads", "1", "-pix_fmt", "yuv420p", str(destination)])

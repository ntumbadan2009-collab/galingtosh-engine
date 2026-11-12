from __future__ import annotations
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.core.validator import validate_film
from app.media.ffmpeg import FFmpegError, probe_media, run_ffmpeg
from app.media.images import normalize_image
from app.media.video import normalize_video

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
        if aw >= ah:
            h, w = short, round(short * aw / ah)
        else:
            w, h = short, round(short * ah / aw)
    return max(2, w - w % 2), max(2, h - h % 2)

def collect_media(film: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["id"]: m for m in film.get("media", []) if isinstance(m, dict) and isinstance(m.get("id"), str)}

class FilmRenderer:
    """Renderer déterministe. Les médias doivent être préalablement résolus en fichiers locaux."""
    def __init__(self, *, max_seconds: int = 600, max_output_mb: int = 45):
        self.max_seconds = max_seconds
        self.max_output_mb = max_output_mb

    async def render(self, film: dict[str, Any], media_files: dict[str, Path], output: Path) -> dict[str, Any]:
        report = validate_film(film)
        if not report["valid"]:
            raise RenderError("Film JSON invalide : " + " ".join(report["errors"][:4]))
        scenes = sorted(film.get("scenes", []), key=lambda x: x.get("order", 0))
        total_duration = sum(float(s.get("durationSec", 0)) for s in scenes)
        if total_duration <= 0:
            raise RenderError("La durée totale du film doit être positive.")
        if total_duration > self.max_seconds:
            raise RenderError(f"Durée demandée supérieure à la limite de {self.max_seconds} secondes.")
        width, height = output_size(film)
        fps = int(min(30, max(1, (film.get("format") or {}).get("fps", 24))))
        media_index = collect_media(film)
        warnings = list(report["warnings"])
        output.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="gt-render-"))
        segments: list[Path] = []
        try:
            for scene_index, scene in enumerate(scenes):
                scene_duration = float(scene.get("durationSec", 0))
                shots = sorted(scene.get("shots", []), key=lambda x: x.get("order", 0))
                cursor = 0.0
                for shot_index, shot in enumerate(shots):
                    start = max(0.0, float(shot.get("inSec", 0)))
                    end = min(scene_duration, float(shot.get("outSec", 0)))
                    if end <= start:
                        continue
                    if start > cursor + 0.02:
                        warnings.append(f"Scène {scene_index+1} : intervalle vide rendu en noir.")
                        black = work / f"segment_{len(segments):04d}.mp4"
                        await self._black(black, width, height, fps, start-cursor)
                        segments.append(black)
                    duration = end - start
                    media_id = shot.get("mediaRef")
                    media = media_index.get(media_id) if media_id else None
                    source = media_files.get(media_id) if media_id else None
                    if media and media.get("kind") == "model3d":
                        warnings.append("Média 3D ignoré : format non pris en charge.")
                        source = None
                    if not source or not source.is_file():
                        warnings.append(f"Plan {shot.get('id', shot_index+1)} : média absent, fond noir utilisé.")
                        segment = work / f"segment_{len(segments):04d}.mp4"
                        await self._black(segment, width, height, fps, duration)
                    else:
                        segment = work / f"segment_{len(segments):04d}.mp4"
                        kind = (media or {}).get("kind")
                        if kind == "image" or source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                            camera = ((shot.get("camera") or {}).get("type") or "none")
                            await normalize_image(source, segment, width, height, fps, duration, camera)
                        elif kind == "video" or source.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                            await normalize_video(source, segment, width, height, fps, start, duration)
                        else:
                            warnings.append(f"Type de média non pris en charge pour le plan {shot_index+1}.")
                            await self._black(segment, width, height, fps, duration)
                    segments.append(segment)
                    cursor = end
                if cursor < scene_duration:
                    warnings.append(f"Scène {scene_index+1} : fin non couverte, fond noir ajouté.")
                    black = work / f"segment_{len(segments):04d}.mp4"
                    await self._black(black, width, height, fps, scene_duration-cursor)
                    segments.append(black)
            if not segments:
                raise RenderError("Aucun plan exploitable dans le Film JSON.")
            transitions = film.get("transitions", []) or []
            if transitions:
                warnings.append("Les transitions déclarées sont temporairement remplacées par des coupes franches dans cette version.")
            concat_list = work / "concat.txt"
            concat_list.write_text("".join(f"file '{p.as_posix()}'\n" for p in segments), encoding="utf-8")
            await run_ffmpeg([
                "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-an", "-c:v", "libx264", "-preset", "veryfast", "-threads", "1",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", str(output)
            ], timeout=self.max_seconds)
            size_mb = output.stat().st_size / (1024 * 1024)
            if size_mb > self.max_output_mb:
                output.unlink(missing_ok=True)
                raise RenderError(f"Fichier final supérieur à la limite de {self.max_output_mb} Mo.")
            probe = await probe_media(str(output))
            streams = probe.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), {})
            return {
                "output": str(output), "duration_seconds": float(probe.get("format", {}).get("duration", 0)),
                "width": video.get("width"), "height": video.get("height"), "fps": fps,
                "size_mb": round(size_mb, 3), "warnings": list(dict.fromkeys(warnings)),
                "audio": False
            }
        except (OSError, FFmpegError) as exc:
            raise RenderError(str(exc)) from None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    async def _black(self, destination: Path, width: int, height: int, fps: int, duration: float):
        await run_ffmpeg([
            "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}",
            "-t", str(duration), "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-threads", "1", "-pix_fmt", "yuv420p", str(destination)
        ])

"""Level-3 editorial gate. Technical checks are not semantic proof."""
from __future__ import annotations
import asyncio
import math
import re
from pathlib import Path
from app.media.ffmpeg import FFmpegError, require_binary

def level3(film: dict) -> bool:
    return (film.get("info") or {}).get("editorialLevel") in {3, 4, 5}

def timeline_issues(film: dict) -> list[str]:
    issues = []
    for i, scene in enumerate(film.get("scenes") or [], 1):
        duration = float(scene["durationSec"])
        cursor = 0.0
        for j, shot in enumerate(sorted(scene.get("shots") or [], key=lambda s: s.get("order", 0)), 1):
            start, end = float(shot["inSec"]), float(shot["outSec"])
            if abs(start-cursor) > 0.08 or end > duration+0.08:
                issues.append(f"Scène {i}, plan {j} : trou, chevauchement ou dépassement du minutage.")
            if end-start < min(1.0, duration)-0.001:
                issues.append(f"Scène {i}, plan {j} : plan trop bref pour une lecture intelligible.")
            cursor = end
        if abs(cursor-duration) > 0.08:
            issues.append(f"Scène {i} : la narration n'est pas entièrement couverte.")
    return issues

async def inspect_render(path: Path, probe: dict, target: float, expect_voice: bool,
                         voice_sources: list[Path], fps: int) -> dict:
    """Decode the actual output. No fabricated visual or speech-quality scores."""
    issues = []
    streams = probe.get("streams", [])
    actual = float(probe.get("format", {}).get("duration", 0))
    tolerance = max(0.4, 4/fps)
    if not math.isfinite(actual) or abs(actual-target)>tolerance:
        issues.append("Durée finale différente de la timeline.")
    if not any(s.get("codec_type") == "video" for s in streams):
        issues.append("Piste vidéo absente.")
    if expect_voice and (not voice_sources or not any(s.get("codec_type") == "audio" for s in streams)):
        issues.append("Narration audio absente.")

    async def scan(source: Path, audio_only: bool = False) -> str:
        filters = ["-vn", "-af", "volumedetect"] if audio_only else [
            "-map", "0:v:0", "-vf", "scale=320:-2,blackdetect=d=0.45:pix_th=0.08:pic_th=0.98", "-an"]
        proc = await asyncio.create_subprocess_exec(
            require_binary("ffmpeg"), "-hide_banner", "-nostats", "-loglevel", "info",
            "-threads", "1", "-filter_threads", "1", "-i", str(source),
            *filters, "-f", "null", "-", stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=max(120, target*3))
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            if proc.returncode is None:
                proc.kill()
            await proc.communicate()
            if isinstance(exc, asyncio.TimeoutError):
                raise FFmpegError("Contrôle qualité : délai dépassé.") from None
            raise
        if proc.returncode:
            raise FFmpegError("Contrôle qualité : décodage impossible.")
        return err.decode("utf-8", "replace")

    log = await scan(path)
    black = [{"start": float(a), "end": float(b)} for a,b in re.findall(
        r"black_start:([\d.]+)\s+black_end:([\d.]+)", log)]
    if black:
        issues.append("Intervalles noirs détectés dans le fichier final.")
    if expect_voice and any(s.get("codec_type") == "audio" for s in streams):
        audio_log = await scan(path, True)
        peak = re.search(r"max_volume:\s*(-?[\d.]+|-inf)\s*dB", audio_log)
        if not peak or float(peak.group(1)) < -45:
            issues.append("Mixage final silencieux ou inaudible.")
    for index, voice in enumerate(voice_sources, 1):
        log = await scan(voice, True)
        match = re.search(r"max_volume:\s*(-?[\d.]+|-inf)\s*dB", log)
        if not match or float(match.group(1)) < -45:
            issues.append(f"Source de narration {index} silencieuse ou inaudible.")
    return {"version": 3, "passed": not issues, "issues": issues,
            "black_intervals": black, "voice_sources_checked": len(voice_sources),
            "duration_seconds": actual, "semantic_review": "not_performed"}

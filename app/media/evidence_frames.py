"""Extract *real* frames across a precisely specified clip passage.

This is evidence extraction only, NOT semantic judging. 3 distinct
timestamps force the reviewing model to inspect more than one thumbnail.
"""
from __future__ import annotations

import asyncio
import base64
import math
import tempfile
from pathlib import Path

from app.media.ffmpeg import FFmpegError, probe_media, require_binary, decoder_env


async def sample_visual_evidence(
    source: Path, source_in_sec: float, duration_sec: float,
) -> dict:
    if not source.is_file():
        raise ValueError("Fichier vidéo absent.")
    if (not math.isfinite(source_in_sec) or source_in_sec < 0 or
            not math.isfinite(duration_sec) or not 1.0 <= duration_sec <= 16.0):
        raise ValueError("Passage vidéo invalide (1 à 16 secondes).")
    probe = await probe_media(str(source))
    if not any(s.get("codec_type") == "video" for s in probe.get("streams", [])):
        raise ValueError("Fichier sans images vidéo.")
    total = float(probe.get("format", {}).get("duration") or 0)
    if not math.isfinite(total) or total <= 0 or source_in_sec+duration_sec > total+0.2:
        raise ValueError("Le passage dépasse la durée réelle du fichier source.")
    ffmpeg = require_binary("ffmpeg")
    positions = [source_in_sec + duration_sec*p for p in (0.17, 0.50, 0.83)]
    frames = []
    with tempfile.TemporaryDirectory(prefix="gt-visual-evidence-") as directory:
        for idx, at in enumerate(positions):
            target = Path(directory) / f"frame_{idx}.jpg"
            cmd = [
                ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
                "-threads", "1", "-filter_threads", "1", "-ss", f"{at:.4f}",
                "-protocol_whitelist", "file,pipe", "-i", str(source), "-frames:v", "1",
                "-vf", "scale='min(480,iw)':-2", "-q:v", "8", "-y", str(target),
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE, env=decoder_env(),
            )
            try:
                _, err = await asyncio.wait_for(process.communicate(), timeout=25)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if process.returncode is None:
                    process.kill()
                await process.communicate()
                raise FFmpegError("Impossible de prélever les images du passage.") from None
            if process.returncode or not target.is_file():
                raise FFmpegError("Échantillon réel du passage indisponible.")
            data = target.read_bytes()
            if not 0 < len(data) < 110_000:
                raise FFmpegError("Échantillon trop volumineux ou vide.")
            frames.append({"atSec": round(at, 3), "jpegBase64": base64.b64encode(data).decode("ascii")})
    return {"analysisLevel": "three_actual_video_frames", "semanticVerified": False,
            "sourceInSec": source_in_sec, "durationSec": duration_sec,
            "sourceDurationSec": total, "frames": frames,
            "limitation": "Trois images ne permettent pas d'attester un mouvement ni une action entre ces images."}

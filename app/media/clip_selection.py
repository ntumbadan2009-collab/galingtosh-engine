"""Low-cost, evidence-based video passage discovery.

Shot boundaries are detected from the actual decoded video. They are not
semantic understanding: the directing agent must review visual content before
claiming that a passage illustrates the narration.
"""
from __future__ import annotations

import asyncio
import math
import re
from pathlib import Path

from app.media.ffmpeg import FFmpegError, probe_media, require_binary

_PTS = re.compile(r"pts_time:\s*([0-9]+(?:\.[0-9]+)?)")
MAX_INSPECTION_SECONDS = 300.0
MAX_CANDIDATES = 120


async def inspect_video_passages(
    source: Path,
    *,
    min_clip_seconds: float = 1.0,
    max_clip_seconds: float = 12.0,
    scene_threshold: float = 0.30,
) -> dict:
    """Find shot-aligned candidate passages; do not invent semantic relevance."""
    if not source.is_file():
        raise ValueError("Fichier vidéo introuvable.")
    if not 0.5 <= min_clip_seconds <= 30:
        raise ValueError("Durée minimale invalide.")
    if not min_clip_seconds <= max_clip_seconds <= 60:
        raise ValueError("Durée maximale invalide.")
    if not 0.1 <= scene_threshold <= 0.8:
        raise ValueError("Seuil de détection invalide.")

    probe = await probe_media(str(source))
    video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("Ce fichier ne contient aucune piste vidéo.")
    try:
        total_seconds = float(probe.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        raise ValueError("Durée de la vidéo indisponible.") from None
    if not math.isfinite(total_seconds) or total_seconds <= 0:
        raise ValueError("Durée de la vidéo invalide.")
    analyzed_seconds = min(total_seconds, MAX_INSPECTION_SECONDS)
    ffmpeg = require_binary("ffmpeg")
    filter_expression = f"scale=320:-2,select=gt(scene\,{scene_threshold:.3f}),showinfo"
    process = await asyncio.create_subprocess_exec(
        ffmpeg, "-hide_banner", "-nostdin", "-threads", "1",
        "-filter_threads", "1", "-loglevel", "info",
        "-i", str(source), "-t", f"{analyzed_seconds:.3f}",
        "-vf", filter_expression, "-an", "-f", "null", "-",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=75)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise FFmpegError("Analyse des changements de plans interrompue.") from None
    if process.returncode != 0:
        raise FFmpegError("Détection des plans impossible.")

    boundaries = [0.0]
    for match in _PTS.finditer(stderr.decode("utf-8", "replace")):
        second = float(match.group(1))
        if boundaries[-1] + 0.15 < second < analyzed_seconds - 0.15:
            boundaries.append(second)
    boundaries.append(analyzed_seconds)
    clips: list[dict] = []
    for start, end in zip(boundaries, boundaries[1:]):
        duration = end - start
        if duration < min_clip_seconds:
            continue
        parts = max(1, math.ceil(duration / max_clip_seconds))
        for index in range(parts):
            part_start = start + duration * index / parts
            part_end = start + duration * (index + 1) / parts
            if part_end - part_start < min_clip_seconds:
                continue
            clips.append({
                "startSec": round(part_start, 3),
                "endSec": round(part_end, 3),
                "durationSec": round(part_end - part_start, 3),
                "evidence": "visual_scene_boundary",
                "semanticVerified": False,
            })
            if len(clips) >= MAX_CANDIDATES:
                break
        if len(clips) >= MAX_CANDIDATES:
            break
    return {
        "durationSec": round(total_seconds, 3),
        "inspectedDurationSec": round(analyzed_seconds, 3),
        "inspectionTruncated": total_seconds > analyzed_seconds,
        "analysisLevel": "shot_boundaries_only",
        "requiresSemanticReview": True,
        "candidates": clips,
    }


def choose_reviewed_passage(
    candidates: list[dict], reviews: list[dict], *,
    minimum_relevance: float = 0.65,
) -> dict | None:
    """Select ONLY a candidate explicitly scored by a visual reviewer.

    A reviewer provides candidateIndex, relevance, visualQuality and
    optionally continuity (each in [0,1]). Unreviewed candidates are never
    advertised as semantically verified.
    """
    if not 0 <= minimum_relevance <= 1:
        raise ValueError("Seuil de pertinence invalide.")
    ranked: list[tuple[float, int, dict]] = []
    for review in reviews:
        if not isinstance(review, dict):
            continue
        index = review.get("candidateIndex")
        if type(index) is not int or index < 0 or index >= len(candidates):
            continue
        values = [review.get("relevance"), review.get("visualQuality"), review.get("continuity", 0.5)]
        if any(not isinstance(v, (float, int)) or isinstance(v, bool)
               or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
            continue
        relevance, quality, continuity = values
        if relevance < minimum_relevance or quality < 0.4:
            continue
        score = 0.65 * relevance + 0.25 * quality + 0.10 * continuity
        ranked.append((score, index, candidates[index]))
    if not ranked:
        return None
    score, index, selected = max(ranked, key=lambda r: (r[0], -r[1]))
    return {**selected, "candidateIndex": index, "reviewScore": round(score, 4),
            "semanticVerified": True, "evidence": "external_visual_review"}

async def sample_candidate_frames(source: Path, candidates: list[dict], *, max_frames: int = 4) -> list[dict]:
    """Return a bounded set of actual JPEG samples for the vision reviewer.

    Samples are drawn across the complete detected timeline. A single frame
    proves only what is visible at that instant, never a whole motion event.
    """
    import base64

    if not 1 <= max_frames <= 6:
        raise ValueError("Nombre d'images d'inspection invalide.")
    if not candidates:
        return []
    count = min(max_frames, len(candidates))
    indices = sorted({round(i * (len(candidates) - 1) / max(1, count - 1)) for i in range(count)})
    ffmpeg = require_binary("ffmpeg")
    samples = []
    for index in indices:
        shot = candidates[index]
        midpoint = (float(shot["startSec"]) + float(shot["endSec"])) / 2
        process = await asyncio.create_subprocess_exec(
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-ss", f"{midpoint:.3f}", "-i", str(source),
            "-frames:v", "1", "-vf", "scale=320:-2",
            "-q:v", "8", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            jpeg, _ = await asyncio.wait_for(process.communicate(), timeout=12)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                process.kill()
            await process.communicate()
            continue
        if process.returncode != 0 or not jpeg.startswith(b"\xff\xd8") or len(jpeg) > 100_000:
            continue
        samples.append({
            "candidateIndex": index,
            "atSec": round(midpoint, 3),
            "jpegBase64": base64.b64encode(jpeg).decode("ascii"),
        })
    return samples

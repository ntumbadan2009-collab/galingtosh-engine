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

from app.media.ffmpeg import FFmpegError, probe_media, require_binary, decoder_env

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
    filter_expression = f"scale=320:-2,select=gt(scene\\,{scene_threshold:.3f}),showinfo"
    process = await asyncio.create_subprocess_exec(
        ffmpeg, "-hide_banner", "-nostdin", "-threads", "1",
        "-filter_threads", "1", "-loglevel", "info",
        "-protocol_whitelist", "file,pipe", "-i", str(source), "-t", f"{analyzed_seconds:.3f}",
        "-vf", filter_expression, "-an", "-f", "null", "-",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=decoder_env(),
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=75)
    except asyncio.TimeoutError:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise FFmpegError("Délai maximal d'analyse vidéo dépassé.") from None
    except asyncio.CancelledError:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
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

async def sample_candidate_frames(
    source: Path,
    candidates: list[dict],
    *,
    analyzed_seconds: float,
    interval_seconds: float = 5.0,
    max_frames: int = 60,
) -> list[dict]:
    """Sample real video frames every five seconds across the inspected window.

    One FFmpeg process extracts all images, avoiding a process launch per frame.
    Each frame maps to the candidate that covers its timestamp. A single image
    cannot verify an action that evolves between frames.
    """
    import base64
    import tempfile

    if not 1 <= max_frames <= 60 or not 1 <= interval_seconds <= 60:
        raise ValueError("Paramètres d'échantillonnage invalides.")
    if not math.isfinite(analyzed_seconds) or analyzed_seconds <= 0:
        raise ValueError("Durée inspectée invalide.")
    if not candidates:
        return []

    window = min(analyzed_seconds, MAX_INSPECTION_SECONDS)
    frame_count = min(max_frames, math.ceil(window / interval_seconds))
    ffmpeg = require_binary("ffmpeg")
    with tempfile.TemporaryDirectory(prefix="galingtosh-frames-") as directory:
        output_pattern = str(Path(directory) / "sample_%04d.jpg")
        process = await asyncio.create_subprocess_exec(
            ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-protocol_whitelist", "file,pipe", "-i", str(source), "-t", f"{window:.3f}",
            "-vf", f"select=isnan(prev_selected_t)+gte(t-prev_selected_t\\,{interval_seconds:g}),scale=320:-2",
            "-fps_mode", "vfr",
            "-frames:v", str(frame_count),
            "-q:v", "9", output_pattern,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=decoder_env(),
        )
        try:
            _, error = await asyncio.wait_for(process.communicate(), timeout=75)
        except asyncio.TimeoutError:
            if process.returncode is None:
                process.kill()
            await process.communicate()
            raise FFmpegError("Délai maximal d'échantillonnage vidéo dépassé.") from None
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
            await process.communicate()
            raise
        if process.returncode != 0:
            raise FFmpegError("Extraction des images de référence impossible.")

        samples = []
        candidate_index = 0
        for index, image_file in enumerate(sorted(Path(directory).glob("sample_*.jpg"))):
            timestamp = index * interval_seconds
            if timestamp >= window:
                break
            while (candidate_index + 1 < len(candidates)
                   and float(candidates[candidate_index]["endSec"]) <= timestamp):
                candidate_index += 1
            candidate = candidates[candidate_index]
            valid_candidate = (float(candidate["startSec"]) <= timestamp
                               < float(candidate["endSec"]))
            jpeg = image_file.read_bytes()
            if not valid_candidate or not jpeg.startswith(b"\xff\xd8") or len(jpeg) > 100_000:
                continue
            samples.append({
                "candidateIndex": candidate_index,
                "atSec": round(timestamp, 3),
                "jpegBase64": base64.b64encode(jpeg).decode("ascii"),
            })
        return samples

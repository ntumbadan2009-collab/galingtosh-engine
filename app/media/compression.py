"""Bound final MP4 size before upload without truncating the timeline.

High-detail 1080p segments may legitimately produce >49 MiB files even when
all shots and voiceovers are correct. A bounded final pass preserves A/V,
resolution, subtitles already burned in, and duration. Intermediate files remain
private to the worker and are only swapped after verifying the candidate.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

from app.media.ffmpeg import FFmpegError, probe_media, run_ffmpeg

logger = logging.getLogger("galingtosh.compression")


async def fit_mp4_to_limit(
    source: Path, max_output_mb: float, *, audio_bitrate_kbps: int = 192,
) -> dict:
    """Return encoding info; only transcode when over the upload size limit."""
    maximum = int(float(max_output_mb) * 1024 * 1024)
    before = source.stat().st_size
    if before <= maximum:
        return {"recompressed": False, "size_before_mb": round(before / 1048576, 3)}

    probe = await probe_media(str(source))
    streams = probe.get("streams", [])
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise FFmpegError("Fichier final sans flux vidéo.")
    audio_present = any(stream.get("codec_type") == "audio" for stream in streams)
    duration = float(probe.get("format", {}).get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise FFmpegError("Durée vidéo finale invalide, compression impossible.")

    # 72% of the hard cap covers VBR peaks, MP4 overhead and soundtrack.
    # The second setting handles unusually complex frames conservatively.
    for number, safety_factor in enumerate((0.72, 0.42), 1):
        candidate = source.with_name(f"{source.stem}.compact-{number}.mp4")
        candidate.unlink(missing_ok=True)
        video_kbps = max(90, min(6000, int(
            (maximum * 8 * safety_factor / duration - (int(audio_bitrate_kbps) + 48) * 1000) / 1000
        )))
        try:
            await run_ffmpeg([
                "-i", str(source), "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
                "-b:v", f"{video_kbps}k",
                "-maxrate", f"{max(120, int(video_kbps * 1.08))}k",
                "-bufsize", f"{max(240, video_kbps * 2)}k",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy", "-movflags", "+faststart",
                str(candidate),
            ], timeout=max(1800, int(duration * 35)))
            candidate_probe = await probe_media(str(candidate))
            candidate_streams = candidate_probe.get("streams", [])
            video_ok = any(s.get("codec_type") == "video" for s in candidate_streams)
            audio_ok = not audio_present or any(
                s.get("codec_type") == "audio" for s in candidate_streams
            )
            candidate_duration = float(candidate_probe.get("format", {}).get("duration") or 0)
            if not video_ok or not audio_ok or abs(candidate_duration - duration) > max(0.8, duration * 0.02):
                raise FFmpegError("La compression a modifié la durée ou perdu une piste.")
            final_size = candidate.stat().st_size
            if final_size <= maximum:
                candidate.replace(source)
                logger.info("final mp4 compressed from %s to %s bytes, target=%sk", before, final_size, video_kbps)
                return {
                    "recompressed": True, "size_before_mb": round(before / 1048576, 3),
                    "size_after_mb": round(final_size / 1048576, 3),
                    "video_bitrate_kbps": video_kbps,
                }
            logger.warning("MP4 compression attempt %s too large: %s > %s bytes", number, final_size, maximum)
        finally:
            candidate.unlink(missing_ok=True)

    raise FFmpegError(f"Impossible de réduire le MP4 sous la limite de {max_output_mb} Mo.")

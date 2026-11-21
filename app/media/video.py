from pathlib import Path
from app.media.ffmpeg import run_ffmpeg, probe_media, FFmpegError
import math

CAMERA_TYPES = {"none", "ken_burns", "dolly", "pan", "tilt", "zoom_in", "zoom_out"}

async def normalize_video(source: Path, destination: Path, width: int, height: int, fps: int,
                         start: float, duration: float, camera: str = "none") -> None:
    if not math.isfinite(start) or start < 0 or not math.isfinite(duration) or duration <= 0:
        raise FFmpegError("Plage temporelle de la vidéo source invalide.")
    probe = await probe_media(str(source))
    video = next((stream for stream in probe.get("streams", [])
                  if stream.get("codec_type") == "video"), None)
    if not video:
        raise FFmpegError("Le média source ne contient pas de flux vidéo.")
    try:
        source_duration = float(probe.get("format", {}).get("duration", 0))
    except (ValueError, TypeError):
        raise FFmpegError("Durée vidéo source inconnue.") from None
    # Do not silently freeze the last frame to cover a wrong edit decision.
    if not math.isfinite(source_duration) or source_duration <= 0 or start + duration > source_duration + 0.06:
        raise FFmpegError(
            f"Passage demandé [{start:.2f}s, {start + duration:.2f}s] "
            f"hors de la vidéo source ({source_duration:.2f}s)."
        )
    camera = camera if camera in CAMERA_TYPES else "none"
    if camera == "none":
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps}"
    else:
        scale = 1.12 if camera in {"ken_burns", "dolly", "pan", "tilt", "zoom_in", "zoom_out"} else 1.0
        sw, sh = int(width * scale), int(height * scale)
        if camera == "pan":
            x = f"(iw-ow)*t/{max(duration,0.1):.4f}"
            y = "(ih-oh)/2"
        elif camera == "tilt":
            x = "(iw-ow)/2"
            y = f"(ih-oh)*t/{max(duration,0.1):.4f}"
        elif camera == "zoom_out":
            x = "(iw-ow)*(1-min(t/" + f"{max(duration,0.1):.4f}" + ",1))/2"
            y = "(ih-oh)*(1-min(t/" + f"{max(duration,0.1):.4f}" + ",1))/2"
        else:
            x = "(iw-ow)/2"
            y = "(ih-oh)/2"
        vf = f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={width}:{height}:x='{x}':y='{y}',setsar=1,fps={fps}"
    await run_ffmpeg([
        "-ss", str(start), "-i", str(source), "-t", str(duration), "-vf", vf + f",tpad=stop_mode=clone:stop_duration={duration}",
        "-an", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)
    ])


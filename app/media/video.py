from pathlib import Path
from app.media.ffmpeg import run_ffmpeg, probe_media, FFmpegError
import math

CAMERA_TYPES = {"none", "ken_burns", "dolly", "pan", "tilt", "zoom_in", "zoom_out"}

async def normalize_video(source: Path, destination: Path, width: int, height: int, fps: int,
                         start: float, duration: float, camera: str = "none") -> str | None:
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
    if not math.isfinite(source_duration) or source_duration <= 0:
        raise FFmpegError("La durée de la vidéo source est invalide.")
    # An agent may request a shot longer than the real source. Recover without
    # introducing a black gap or silently freezing the last image. Prefer
    # controlled slow motion when feasible; repeat only for large shortages.
    # Report any fallback to the renderer so the deliverable remains auditable.
    adjustment = None
    if start >= source_duration - 0.10:
        adjustment = (
            f"Début source {start:.2f}s indisponible (durée {source_duration:.2f}s) : "
            "lecture reprise à 0s."
        )
        start = 0.0
    available = source_duration - start
    if available < 0.25:
        raise FFmpegError("La vidéo ne contient pas assez d'images exploitables.")
    time_scale = 1.0
    loop_source = False
    if duration > available + 0.06:
        stretch = duration / available
        if stretch <= 1.6:
            time_scale = stretch
            adjustment = (
                f"Vidéo source de {available:.2f}s adaptée au plan de {duration:.2f}s "
                f"par ralentissement {1/stretch:.2f}x."
            )
        else:
            loop_source = True
            adjustment = (
                f"Vidéo source de {available:.2f}s insuffisante pour {duration:.2f}s : "
                "lecture répétée ; rechercher une séquence complémentaire pour améliorer le montage."
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
    # Slow down timestamps before FPS conversion; avoid frame freezes used by
    # the old tpad=duration fallback. A tiny tail pad covers codec rounding only.
    if time_scale != 1.0:
        vf = f"setpts={time_scale:.8f}*(PTS-STARTPTS)," + vf
    inputs = (["-stream_loop", "-1"] if loop_source else []) + [
        "-ss", str(start), "-i", str(source),
    ]
    await run_ffmpeg([
        *inputs, "-t", str(duration),
        "-vf", vf + ",tpad=stop_mode=clone:stop_duration=0.12",
        "-an", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)
    ])
    return adjustment


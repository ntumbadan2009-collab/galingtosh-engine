from pathlib import Path
from app.media.ffmpeg import run_ffmpeg

CAMERA_TYPES = {"none", "ken_burns", "dolly", "pan", "tilt", "zoom_in", "zoom_out"}

async def normalize_video(source: Path, destination: Path, width: int, height: int, fps: int,
                         start: float, duration: float, camera: str = "none") -> None:
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
        "-ss", str(start), "-i", str(source), "-t", str(duration), "-vf", vf,
        "-an", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)
    ])

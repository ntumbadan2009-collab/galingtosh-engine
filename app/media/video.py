from pathlib import Path
from app.media.ffmpeg import run_ffmpeg

async def normalize_video(source: Path, destination: Path, width: int, height: int, fps: int, start: float, duration: float) -> None:
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps}"
    await run_ffmpeg([
        "-ss", str(start), "-i", str(source), "-t", str(duration), "-vf", vf,
        "-an", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)
    ])

from pathlib import Path
from app.media.ffmpeg import run_ffmpeg

async def normalize_image(source: Path, destination: Path, width: int, height: int, fps: int, duration: float, camera: str = "none") -> None:
    frames = max(1, round(duration * fps))
    motion = {
        "ken_burns": "zoompan=z='min(zoom+0.0008,1.12)':d=1:s={w}x{h}:fps={fps}",
        "zoom_in": "zoompan=z='min(zoom+0.001,1.15)':d=1:s={w}x{h}:fps={fps}",
        "zoom_out": "zoompan=z='if(eq(on,1),1.15,max(1.0,zoom-0.001))':d=1:s={w}x{h}:fps={fps}",
        "pan": "zoompan=z='1.12':x='(iw-iw/zoom)*on/{frames}':y='(ih-ih/zoom)/2':d=1:s={w}x{h}:fps={fps}",
        "tilt": "zoompan=z='1.12':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*on/{frames}':d=1:s={w}x{h}:fps={fps}",
        "dolly": "zoompan=z='min(zoom+0.0007,1.10)':d=1:s={w}x{h}:fps={fps}",
    }
    vf = "scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1".format(
        sw=width, sh=height, w=width, h=height
    )
    if camera in motion:
        vf += "," + motion[camera].format(w=width, h=height, fps=fps, frames=frames)
    else:
        vf += ",fps={}".format(fps)
    await run_ffmpeg([
        "-loop", "1", "-i", str(source), "-t", str(duration), "-vf", vf,
        "-an", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)
    ])

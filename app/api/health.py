import shutil
import subprocess
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok", "service": "galingtosh-engine"}

@router.get("/capabilities")
async def capabilities():
    binary = shutil.which("ffmpeg")
    version = None
    if binary:
        try:
            p = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=2, check=False)
            version = p.stdout.splitlines()[0] if p.stdout else None
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {
        "service": "galingtosh-engine",
        "ffmpeg": {"available": bool(binary), "version": version},
        "cameras": ["ken_burns", "dolly", "pan", "tilt", "zoom_in", "zoom_out", "none"],
        "transitions": ["cut", "dissolve", "fade", "slide", "zoom", "wipe"],
        "effects": ["fade_in", "fade_out", "grayscale", "vignette", "text_overlay"],
        "tts": {"providers": [], "status": "not_configured"},
        "limits": {"max_render_seconds": 600, "max_output_mb": 45, "resolutions": ["720p"]},
        "rendering": "not_implemented_yet"
    }

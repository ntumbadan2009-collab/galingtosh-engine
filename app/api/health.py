import shutil
import os
import subprocess
from fastapi import APIRouter
from app.config import get_settings

router=APIRouter()

@router.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def service_root():
    """Give the public service URL a truthful status page instead of a 404."""
    return {
        "service": "galingtosh-engine",
        "status": "running",
        "message": "API de rendu audiovisuel; ce service ne fournit pas l'application mobile.",
        "endpoints": {
            "health": "/health",
            "capabilities": "/capabilities",
            "documentation": "/docs",
        },
    }

@router.get("/health")
async def health():
    return {"status":"ok","service":"galingtosh-engine","revision":os.getenv("RENDER_GIT_COMMIT", "local"),"workflow_version":2}

@router.get("/capabilities")
async def capabilities():
    settings=get_settings(); binary=shutil.which("ffmpeg"); version=None
    if binary:
        try:
            result=subprocess.run([binary,"-version"],capture_output=True,text=True,timeout=2,check=False)
            version=result.stdout.splitlines()[0] if result.stdout else None
        except (OSError,subprocess.TimeoutExpired): pass
    return {"service":"galingtosh-engine","ffmpeg":{"available":bool(binary),"version":version},
        "rendering":"deterministic_ffmpeg" if binary else "unavailable",
        "media":["image","video","audio","svg","chart"],
        "cameras":["ken_burns","dolly","pan","tilt","zoom_in","zoom_out","none"],
        "transitions":["cut","dissolve","fade","slide","zoom","wipe"],
        "audio":{"supported":True,"formats":["mp3","m4a","wav","ogg","aac","flac"],"mixing":True},
        "subtitles":{"supported":True,"mode":"burned_in","formats":["srt"]},
        "effects":["fade_in","fade_out","grayscale","vignette","text_overlay"],
        "graphics":{"charts":True,"svg":True,"3d":False},
        "tts":{"primary":"edge-tts","fallback":"piper-local-fr","status":"network_primary_with_local_fallback"},
        "limits":{"max_render_seconds":settings.max_render_seconds,"max_output_mb":settings.max_output_mb,
            "resolutions":["720p","1080p"],"max_pixels":2073600,"concurrent_renders":1}}

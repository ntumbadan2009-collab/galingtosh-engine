from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_binary(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise FFmpegError(f"{name} est absent de l'environnement.")
    return binary


async def run_ffmpeg(args: list[str], *, timeout: int = 600) -> None:
    binary = require_binary("ffmpeg")
    proc = await asyncio.create_subprocess_exec(
        binary, "-hide_banner", "-loglevel", "error", "-y", *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise FFmpegError("Délai maximal FFmpeg dépassé.") from None
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip().splitlines()
        raise FFmpegError("Échec FFmpeg : " + (detail[-1][:180] if detail else "erreur inconnue"))


async def probe_media(path: str) -> dict:
    binary = require_binary("ffprobe")
    proc = await asyncio.create_subprocess_exec(
        binary, "-v", "error", "-show_streams", "-show_format", "-of", "json", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise FFmpegError("Délai maximal ffprobe dépassé.") from None
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    if proc.returncode:
        raise FFmpegError("Impossible d'analyser le média.")
    import json
    try:
        return json.loads(stdout)
    except ValueError:
        raise FFmpegError("Réponse ffprobe invalide.") from None

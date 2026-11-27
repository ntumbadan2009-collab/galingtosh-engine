from __future__ import annotations

import asyncio
import shutil
import os
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_binary(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise FFmpegError(f"{name} est absent de l'environnement.")
    return binary


def decoder_env() -> dict[str,str]:
    # Do not pass Supabase/API credentials to media decoders.
    return {"PATH":os.defpath + ":/usr/local/bin","LANG":"C.UTF-8","HOME":"/tmp"}

def local_inputs(args: list[str]) -> list[str]:
    out=[]
    for value in args:
        if value == "-i":
            out += ["-protocol_whitelist","file,pipe"]
        out.append(value)
    return out

async def run_ffmpeg(args: list[str], *, timeout: int = 1800) -> None:
    binary = require_binary("ffmpeg")
    proc = await asyncio.create_subprocess_exec(
        binary, "-hide_banner", "-loglevel", "error", "-y", "-filter_threads", "1", "-filter_complex_threads", "1", *local_inputs(args),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=decoder_env(),
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
        # Keep a small diagnostic tail so a production render failure can be
        # fixed from its job error/logs instead of reducing every FFmpeg fault
        # to the generic final line.
        diagnostic = " | ".join(line.strip() for line in detail[-6:])
        raise FFmpegError("Échec FFmpeg : " + (diagnostic[:900] if diagnostic else "erreur inconnue"))


async def probe_media(path: str, *, input_format: str | None = None) -> dict:
    binary = require_binary("ffprobe")
    proc = await asyncio.create_subprocess_exec(
        binary, "-v", "error", "-protocol_whitelist", "file,pipe", *(["-f",input_format] if input_format else []), "-show_streams", "-show_format", "-of", "json", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=decoder_env(),
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

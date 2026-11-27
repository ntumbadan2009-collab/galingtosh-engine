"""Opt-in external media gate. No executable/HTML/playlist/3D archive imports."""
from __future__ import annotations
import asyncio, base64, hashlib, io, os, warnings
from pathlib import Path
from PIL import Image, ImageOps
from app.media.resolver import download_public_media
from app.media.ffmpeg import probe_media, run_ffmpeg

SOURCES = {"artic": ("artic.edu",), "archive": ("archive.org",), "smithsonian": ("ids.si.edu","3d-api.si.edu")}
LICENSES = {"CC0 1.0", "CC BY 4.0", "CC BY 3.0", "CC BY 2.5", "CC BY 2.0", "CC BY 1.0", "Public Domain Mark 1.0"}

def is_extended(row: dict) -> bool:
    return (row.get("provenance") or {}).get("source") in SOURCES

def digest(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def identify(path: Path, kind: str, mime: str) -> None:
    with path.open("rb") as f:
        prefix = f.read(32)
    if kind == "video":
        ok = mime in {"video/mp4", "application/octet-stream"} and len(prefix) >= 12 and prefix[4:8] == b"ftyp"
    elif kind == "image":
        ok = ((mime in {"image/jpeg","application/octet-stream"} and prefix.startswith(b"\xff\xd8\xff")) or
              (mime in {"image/png","application/octet-stream"} and prefix.startswith(b"\x89PNG\r\n\x1a\n")) or
              (mime in {"image/webp","application/octet-stream"} and prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP"))
    else:
        ok = False
    if not ok:
        raise ValueError("Signature de fichier Web non autorisée.")

def clean_image(source: Path, output: Path, size: int = 1920) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source, formats=["JPEG","PNG","WEBP"]) as original:
            if original.width * original.height > 20_000_000 or getattr(original,"n_frames",1) != 1:
                raise ValueError("Image Web trop grande ou animée.")
            original.load()
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((size,size))
            image.save(output, "JPEG", quality=86, optimize=True)

async def download_extended(row: dict, target: Path) -> tuple[int,str]:
    if os.getenv("SECURE_WEB_MEDIA_ENABLED") != "true":
        raise ValueError("Import Web en quarantaine.")
    p = row.get("provenance") or {}
    kind = row.get("kind")
    if p.get("source") not in SOURCES or p.get("license") not in LICENSES or not p.get("author"):
        raise ValueError("Provenance ou droits Web incomplets.")
    limit = 45*1024*1024 if kind == "video" else 12*1024*1024
    try:
        count,mime = await download_public_media(p["download_url"],target,limit,allowed_hosts=SOURCES[p["source"]])
        identify(target,kind,mime)
        if kind == "video":
            data=await probe_media(str(target),input_format="mov")
            streams=data.get("streams",[])
            videos=[s for s in streams if s.get("codec_type")=="video"]
            if len(videos)!=1 or any(s.get("codec_type") not in {"video","audio"} for s in streams):
                raise ValueError("Flux vidéo Web non autorisé.")
            v=videos[0]
            if v.get("codec_name") not in {"h264","hevc","mpeg4"} or not 1<=int(v.get("width",0))*int(v.get("height",0))<=3840*2160 or not 0<float(data.get("format",{}).get("duration",0))<=600:
                raise ValueError("Codec, taille ou durée Web non autorisés.")
            return count,"video/mp4"
        return count,mime
    except BaseException:
        target.unlink(missing_ok=True)
        raise

async def contact_sheet(source:Path, target:Path, start:float, duration:float) -> str:
    # Dense sampled contact sheet of the exact passage; not proof for all frames.
    await run_ffmpeg(["-ss",str(start),"-t",str(duration),"-f","mov","-i",str(source),
        "-an","-sn","-dn","-vf","fps=2,scale=240:136:force_original_aspect_ratio=decrease,pad=240:136:(ow-iw)/2:(oh-ih)/2,tile=4x8:padding=2:margin=2",
        "-frames:v","1","-q:v","6",str(target)],timeout=40)
    payload=target.read_bytes()
    if not 0<len(payload)<=480000: raise ValueError("Planche de sécurité trop volumineuse.")
    return base64.b64encode(payload).decode("ascii")

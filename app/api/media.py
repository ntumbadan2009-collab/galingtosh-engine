from __future__ import annotations
import shutil
import tempfile
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from app.security import require_engine_secret
from app.media.resolver import download_public_media
from app.media.ffmpeg import probe_media, FFmpegError
from app.storage.supabase import SupabaseREST

router = APIRouter(prefix="/media", dependencies=[Depends(require_engine_secret)])

class ProbeRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=80)
    media_id: str = Field(min_length=1, max_length=80)
    user_id: str = Field(min_length=1, max_length=80)

@router.post("/probe")
async def probe(request: Request, payload: ProbeRequest) -> dict[str, Any]:
    db = getattr(request.app.state, "supabase", None)
    if not isinstance(db, SupabaseREST):
        raise HTTPException(status_code=503, detail="Stockage média indisponible.")
    rows = await db.read_media_assets(payload.project_id, [payload.media_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Média introuvable.")
    row = rows[0]
    kind = str(row.get("kind") or "")
    source = str(row.get("source") or "")
    if kind not in {"image", "video", "audio"}:
        raise HTTPException(status_code=422, detail="Ce type de média ne peut pas être analysé par ffprobe.")
    directory = Path(tempfile.mkdtemp(prefix="galingtosh-probe-"))
    target = directory / "source"
    try:
        if source == "upload":
            await db.download_user_upload(str(row.get("storage_path") or ""), payload.user_id, target, 200 * 1024 * 1024)
        elif source == "search":
            provenance = row.get("provenance") or {}
            url = provenance.get("download_url") or provenance.get("preview_url")
            if not url:
                raise HTTPException(status_code=422, detail="URL du média absente.")
            await download_public_media(str(url), target, 200 * 1024 * 1024)
        else:
            raise HTTPException(status_code=422, detail="Source média non prise en charge.")
        result = await probe_media(str(target))
        streams = result.get("streams", [])
        return {
            "media_id": payload.media_id,
            "format": result.get("format", {}).get("format_name"),
            "duration_seconds": result.get("format", {}).get("duration"),
            "size_bytes": result.get("format", {}).get("size"),
            "streams": [{
                "type": stream.get("codec_type"),
                "codec": stream.get("codec_name"),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "sample_rate": stream.get("sample_rate"),
                "channels": stream.get("channels"),
                "frame_rate": stream.get("avg_frame_rate"),
            } for stream in streams],
        }
    except HTTPException:
        raise
    except (OSError, ValueError, FFmpegError):
        raise HTTPException(status_code=422, detail="Le média ne peut pas être analysé.") from None
    finally:
        shutil.rmtree(directory, ignore_errors=True)

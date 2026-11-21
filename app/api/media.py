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
user_router = APIRouter(prefix="/media")

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


class InspectClipsRequest(ProbeRequest):
    min_clip_seconds: float = Field(default=1.0, ge=0.5, le=30)
    max_clip_seconds: float = Field(default=12.0, ge=0.5, le=60)
    scene_threshold: float = Field(default=0.30, ge=0.1, le=0.8)
    include_sample_frames: bool = False


@user_router.post("/inspect-clips")
async def inspect_clips(request: Request, payload: InspectClipsRequest) -> dict[str, Any]:
    """Return actual shot boundaries, not fabricated semantic assessments.

    The directing agent must visually review candidates before selecting one.
    """
    from app.media.clip_selection import inspect_video_passages, sample_candidate_frames

    if payload.max_clip_seconds < payload.min_clip_seconds:
        raise HTTPException(status_code=422, detail="Durée maximale inférieure au minimum.")
    db = getattr(request.app.state, "supabase", None)
    if not isinstance(db, SupabaseREST):
        raise HTTPException(status_code=503, detail="Stockage média indisponible.")
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    authenticated_id = await db.authenticated_user_id(token)
    if not authenticated_id or authenticated_id != payload.user_id:
        raise HTTPException(status_code=401, detail="Session invalide.")
    rows = await db.read_media_assets(payload.project_id, [payload.media_id])
    if not rows or str(rows[0].get("user_id")) != authenticated_id:
        raise HTTPException(status_code=404, detail="Média introuvable.")
    row = rows[0]
    if row.get("kind") != "video":
        raise HTTPException(status_code=422, detail="Analyse réservée aux vidéos.")
    directory = Path(tempfile.mkdtemp(prefix="galingtosh-clips-"))
    target = directory / "source"
    try:
        if row.get("source") == "upload":
            await db.download_user_upload(str(row.get("storage_path") or ""),
                                          payload.user_id, target, 200 * 1024 * 1024)
        elif row.get("source") == "search":
            provenance = row.get("provenance") or {}
            url = provenance.get("download_url") or provenance.get("preview_url")
            if not url:
                raise HTTPException(status_code=422, detail="URL du média absente.")
            await download_public_media(str(url), target, 200 * 1024 * 1024)
        else:
            raise HTTPException(status_code=422, detail="Source média non prise en charge.")
        result = await inspect_video_passages(
            target, min_clip_seconds=payload.min_clip_seconds,
            max_clip_seconds=payload.max_clip_seconds,
            scene_threshold=payload.scene_threshold,
        )
        if payload.include_sample_frames:
            result["sampleFrames"] = await sample_candidate_frames(
                target, result.get("candidates", []), max_frames=3
            )
        return {"mediaId": payload.media_id, **result}
    except HTTPException:
        raise
    except (OSError, ValueError, FFmpegError):
        raise HTTPException(status_code=422, detail="Analyse des passages impossible.") from None
    finally:
        shutil.rmtree(directory, ignore_errors=True)

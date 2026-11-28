from __future__ import annotations
import shutil
import base64
import asyncio
import tempfile
from pathlib import Path
from PIL import Image
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from app.security import require_engine_secret
from app.media.resolver import download_public_media
from app.media.secure_web import is_extended, download_extended, clean_image, digest, contact_sheet
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
            await (download_extended(row, target) if is_extended(row) else download_public_media(str(url), target, 200 * 1024 * 1024))
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
    mission_id = request.headers.get("X-Production-Mission", "")
    authenticated_id = (await db.production_user_id(token, mission_id) if mission_id
                        else await db.authenticated_user_id(token))
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
            await (download_extended(row, target) if is_extended(row) else download_public_media(str(url), target, 200 * 1024 * 1024))
        else:
            raise HTTPException(status_code=422, detail="Source média non prise en charge.")
        result = await inspect_video_passages(
            target, min_clip_seconds=payload.min_clip_seconds,
            max_clip_seconds=payload.max_clip_seconds,
            scene_threshold=payload.scene_threshold,
        )
        if payload.include_sample_frames:
            result["sampleFrames"] = await sample_candidate_frames(
                target, result.get("candidates", []),
                analyzed_seconds=result["inspectedDurationSec"],
                interval_seconds=5.0, max_frames=60
            )
        return {"mediaId": payload.media_id, **result}
    except HTTPException:
        raise
    except (OSError, ValueError, FFmpegError):
        raise HTTPException(status_code=422, detail="Analyse des passages impossible.") from None
    finally:
        shutil.rmtree(directory, ignore_errors=True)


class EvidenceFramesRequest(ProbeRequest):
    source_in_sec: float = Field(default=0, ge=0, le=3600)
    duration_sec: float = Field(ge=1.0, le=16.0)


@user_router.post("/evidence-frames")
async def evidence_frames(request: Request, payload: EvidenceFramesRequest) -> dict[str, Any]:
    """Three actual frames for agent-side relevance review; NOT a semantic verdict."""
    from app.media.evidence_frames import sample_visual_evidence

    db = getattr(request.app.state, "supabase", None)
    if not isinstance(db, SupabaseREST):
        raise HTTPException(status_code=503, detail="Stockage média indisponible.")
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    mission_id = request.headers.get("X-Production-Mission", "")
    authenticated = (await db.production_user_id(token, mission_id) if mission_id
                     else await db.authenticated_user_id(token))
    if not authenticated or authenticated != payload.user_id:
        raise HTTPException(status_code=401, detail="Session invalide.")
    rows = await db.read_media_assets(payload.project_id, [payload.media_id])
    if not rows or str(rows[0].get("user_id")) != authenticated:
        raise HTTPException(status_code=404, detail="Média introuvable.")
    media = rows[0]
    if media.get("kind") != "video":
        raise HTTPException(status_code=422, detail="La preuve par images exige une vidéo.")
    directory = Path(tempfile.mkdtemp(prefix="galingtosh-evidence-"))
    target = directory / "source"
    try:
        if media.get("source") == "upload":
            await db.download_user_upload(
                str(media.get("storage_path") or ""), authenticated, target, 200*1024*1024
            )
        elif media.get("source") == "search":
            provenance = media.get("provenance") or {}
            url = provenance.get("download_url") or provenance.get("preview_url")
            if not url:
                raise HTTPException(status_code=422, detail="URL source absente.")
            await (download_extended(media, target) if is_extended(media) else download_public_media(str(url), target, 200*1024*1024))
        else:
            raise HTTPException(status_code=422, detail="Source média non prise en charge.")
        result = await sample_visual_evidence(target, payload.source_in_sec, payload.duration_sec)
        if is_extended(media):
            result["sha256"] = await asyncio.to_thread(digest,target)
            result["safetyContactSheet"] = await contact_sheet(target,directory/"sheet.jpg",payload.source_in_sec,payload.duration_sec)
        return {"mediaId":payload.media_id,**result}
    except HTTPException:
        raise
    except (OSError, ValueError, FFmpegError):
        raise HTTPException(status_code=422, detail="Échantillonnage du passage impossible.") from None
    finally:
        shutil.rmtree(directory, ignore_errors=True)


class AudioEvidenceRequest(ProbeRequest):
    source_in_sec: float = Field(default=0,ge=0,le=3600)
    duration_sec: float = Field(ge=.25,le=12)

@user_router.post("/audio-evidence")
async def audio_evidence(request:Request,payload:AudioEvidenceRequest)->dict[str,Any]:
    from app.media.audio_evidence import licensed_public_sound,extract_audio_clip,MAX_SOUND_BYTES
    db=getattr(request.app.state,"supabase",None)
    if not isinstance(db,SupabaseREST):raise HTTPException(status_code=503,detail="Stockage indisponible.")
    token=request.headers.get("Authorization","").removeprefix("Bearer ").strip()
    mission_id=request.headers.get("X-Production-Mission","")
    authenticated=(await db.production_user_id(token,mission_id) if mission_id else await db.authenticated_user_id(token))
    if not authenticated or authenticated!=payload.user_id:raise HTTPException(status_code=401,detail="Session invalide.")
    rows=await db.read_media_assets(payload.project_id,[payload.media_id])
    if not rows or str(rows[0].get("user_id"))!=authenticated:raise HTTPException(status_code=404,detail="Média introuvable.")
    row=rows[0]
    if not licensed_public_sound(row):raise HTTPException(status_code=422,detail="Seul un fichier audio public original CC0 ou CC BY, avec attribution, peut être contrôlé.")
    directory=Path(tempfile.mkdtemp(prefix="gt-sound-evidence-"))
    try:
        target=directory/"source"
        _,mime=await download_public_media(row["provenance"]["download_url"],target,MAX_SOUND_BYTES)
        if not mime.startswith("audio/"):raise ValueError("Type MIME non audio.")
        return {"mediaId":payload.media_id,**await extract_audio_clip(target,payload.source_in_sec,payload.duration_sec,directory/"clip.wav")}
    except (OSError,ValueError,FFmpegError):
        raise HTTPException(status_code=422,detail="Extrait audio réel non exploitable.") from None
    finally:shutil.rmtree(directory,ignore_errors=True)

@user_router.post("/image-evidence")
@user_router.post("/secure-image-evidence")
async def secure_image_evidence(request:Request,payload:ProbeRequest)->dict[str,Any]:
    db=getattr(request.app.state,"supabase",None)
    if not isinstance(db,SupabaseREST):raise HTTPException(status_code=503,detail="Stockage indisponible.")
    token=request.headers.get("Authorization","").removeprefix("Bearer ").strip()
    mission=request.headers.get("X-Production-Mission","")
    uid=await (db.production_user_id(token,mission) if mission else db.authenticated_user_id(token))
    if not uid or uid!=payload.user_id:raise HTTPException(status_code=401,detail="Session invalide.")
    rows=await db.read_media_assets(payload.project_id,[payload.media_id])
    if not rows or rows[0].get("user_id")!=uid or rows[0].get("kind")!="image":
        raise HTTPException(status_code=404,detail="Image Web introuvable.")
    with tempfile.TemporaryDirectory(prefix="gt-secure-image-") as work:
        source=Path(work)/"raw"; thumb=Path(work)/"proof.jpg"
        try:
            row=rows[0]
            if is_extended(row):
                await download_extended(row,source)
            elif row.get("source")=="upload":
                await db.download_user_upload(str(row.get("storage_path") or ""),uid,source,12*1024*1024)
            elif row.get("source")=="search":
                p=row.get("provenance") or {}
                url=p.get("download_url") or p.get("preview_url")
                if not url or not p.get("license") or not p.get("author") or not p.get("url"):
                    raise ValueError("Provenance incomplète.")
                await download_public_media(str(url),source,12*1024*1024)
            else:
                raise ValueError("Source non prise en charge.")
            await asyncio.to_thread(clean_image,source,thumb,480)
            return {"sha256":await asyncio.to_thread(digest,source),"jpegBase64":base64.b64encode(thumb.read_bytes()).decode("ascii")}
        except (OSError,ValueError,FFmpegError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            raise HTTPException(status_code=422,detail="Image inaccessible ou format non autorisé.") from None

class LicensedWebRequest(BaseModel):
    user_id: str = Field(min_length=1,max_length=80)
    urls: list[str] = Field(min_length=1,max_length=3)
    kind: str

@user_router.post("/licensed-web-candidates")
async def licensed_web_candidates(request:Request,payload:LicensedWebRequest):
    from app.media.licensed_web import licensed_page_candidates
    db=getattr(request.app.state,"supabase",None)
    if not isinstance(db,SupabaseREST):raise HTTPException(status_code=503,detail="Stockage indisponible.")
    token=request.headers.get("Authorization","").removeprefix("Bearer ").strip()
    mission=request.headers.get("X-Production-Mission","")
    if not mission:raise HTTPException(status_code=401,detail="Mission requise.")
    uid=await db.production_user_id(token,mission)
    if not uid or uid!=payload.user_id:raise HTTPException(status_code=401,detail="Mission invalide.")
    if payload.kind not in {"image","video"}:raise HTTPException(status_code=422,detail="Type non pris en charge.")
    rows=await asyncio.gather(*(licensed_page_candidates(url,payload.kind) for url in payload.urls),return_exceptions=True)
    return {"results":[x for row in rows if isinstance(row,list) for x in row][:6]}

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.media.tts import release_piper_voice, synthesize_text_with_provider, voice_direction

router = APIRouter(prefix="/narration", tags=["narration"])
_rate: dict[str, list[float]] = {}
logger = logging.getLogger("galingtosh.narration_api")


@router.post("/measure")
async def measure(payload: dict[str, Any], request: Request):
    authorization = request.headers.get("Authorization", "")
    token = re.sub(r"^Bearer\s+", "", authorization, flags=re.IGNORECASE).strip()
    db = request.app.state.supabase
    mission_id = request.headers.get("X-Production-Mission", "")
    user_id = (await db.production_user_id(token, mission_id) if mission_id
               else await db.authenticated_user_id(token))
    if not user_id:
        raise HTTPException(status_code=401, detail="Session utilisateur invalide.")

    now = time.monotonic()
    recent = [at for at in _rate.get(user_id, []) if now - at < 300]
    if len(recent) >= 8:
        raise HTTPException(status_code=429, detail="Trop de mesures TTS rapprochées; réessaie dans quelques minutes.")

    segments = payload.get("segments")
    if not isinstance(segments, list) or not 1 <= len(segments) <= 20:
        raise HTTPException(status_code=422, detail="Fournis de 1 à 20 segments de narration.")
    ids = [str(s.get("sceneId", "")) for s in segments if isinstance(s, dict)]
    if len(ids) != len(segments) or any(not i or len(i) > 80 for i in ids) or len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="Chaque segment doit désigner une scène unique.")
    for segment in segments:
        if not isinstance(segment.get("text"), str) or not segment["text"].strip() or len(segment["text"]) > 4000:
            raise HTTPException(status_code=422, detail="Chaque narration doit contenir de 1 à 4000 caractères.")
        try:
            voice_direction(segment.get("ratePercent",0),segment.get("pitchHz",0))
        except ValueError as exc:
            raise HTTPException(status_code=422,detail=str(exc)) from None
        target = segment.get("targetDurationSec")
        if target is not None and (not isinstance(target, (int, float)) or isinstance(target, bool) or not 0.5 <= target <= 3600):
            raise HTTPException(status_code=422, detail="Durée cible de narration invalide.")

    _rate[user_id] = recent + [now]
    results = []
    try:
        with TemporaryDirectory(prefix="gt-tts-measure-") as temp:
            root = Path(temp)
            for index, segment in enumerate(segments):
                try:
                    seconds, provider = await synthesize_text_with_provider(segment["text"],
                        str(segment.get("language") or "fr"), segment.get("voice"),
                        root / f"scene-{index}.mp3", str(segment.get("ttsProvider") or "edge-tts"),
                        segment.get("ratePercent",0),segment.get("pitchHz",0))
                except Exception as exc:
                    logger.warning("Mesure TTS scène %d échouée : %s.", index + 1, str(exc)[:240])
                    raise HTTPException(status_code=503, detail=f"La durée TTS de la scène {index + 1} n'a pas pu être mesurée.") from None
                target = segment.get("targetDurationSec")
                results.append({"sceneId": str(segment["sceneId"]), "durationSec": round(seconds, 3),
                    "targetDurationSec": float(target) if target is not None else None,
                    "ttsProvider": provider,
                    "deltaSec": round(seconds - float(target), 3) if target is not None else None})
    finally:
        release_piper_voice()
    return {"segments": results}

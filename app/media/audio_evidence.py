"""Decode licensed, real sound clips and bind approval to their source bytes."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import math
import re
import wave
from array import array
from pathlib import Path
from urllib.parse import urlsplit
from app.media.ffmpeg import probe_media,run_ffmpeg
from app.core.narrative_policy import excerpt_matches

MAX_SOUND_BYTES=20*1024*1024
HASH=re.compile(r"^[0-9a-f]{64}$")
LICENSE_PATH=re.compile(r"/(?:licenses/by/(?:1\.0|2\.0|2\.5|3\.0|4\.0)|publicdomain/zero/1\.0)/?")

def licensed_public_sound(row:dict)->bool:
    p=row.get("provenance") or {}
    try:
        url=urlsplit(p.get("license_url") or "")
        return (row.get("kind")=="audio" and row.get("source")=="search"
            and p.get("source") in {"wikimedia","openverse"}
            and url.scheme in {"https","http"} and url.netloc=="creativecommons.org"
            and not url.query and not url.fragment and bool(LICENSE_PATH.fullmatch(url.path))
            and isinstance(p.get("download_url"),str) and p["download_url"].startswith("https://")
            and isinstance(p.get("author"),str) and bool(p["author"].strip())
            and p["author"] not in {"Auteur non précisé","Auteur non renseigné"}
            and isinstance(p.get("attribution"),str) and bool(p["attribution"].strip())
            and isinstance(p.get("url"),str) and p["url"].startswith("https://"))
    except (ValueError,TypeError,AttributeError):
        return False

def _hash(path:Path)->str:
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

async def extract_audio_clip(source:Path,start:float,duration:float,target:Path)->dict:
    if not source.is_file() or not 0<source.stat().st_size<=MAX_SOUND_BYTES:
        raise ValueError("Fichier son absent ou trop volumineux.")
    if not math.isfinite(start) or not math.isfinite(duration) or not 0<=start<=3600 or not .25<=duration<=12:
        raise ValueError("Extrait sonore hors limites.")
    probe=await probe_media(str(source))
    audio=next((s for s in probe.get("streams",[]) if s.get("codec_type")=="audio"),None)
    if audio is None:raise ValueError("Aucune piste audio réelle.")
    length=float(audio.get("duration") or probe.get("format",{}).get("duration") or 0)
    if not math.isfinite(length) or start+duration>length+.03:raise ValueError("Extrait au-delà de la piste audio.")
    await run_ffmpeg(["-ss",f"{start:.6f}","-i",str(source),"-map","0:a:0","-t",f"{duration:.6f}",
                      "-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(target)],timeout=30)
    with wave.open(str(target),"rb") as w:
        samples=array("h");samples.frombytes(w.readframes(w.getnframes()))
        if __import__("sys").byteorder!="little":samples.byteswap()
        measured=w.getnframes()/w.getframerate()
    if abs(measured-duration)>.04 or not samples or max(abs(s) for s in samples)<500:
        raise ValueError("Effet trop silencieux ou extrait incomplet.")
    return {"sourceSha256":await asyncio.to_thread(_hash,source),"sourceInSec":start,
            "durationSec":duration,"measuredSeconds":measured,"mimeType":"audio/wav",
            "audioBase64":base64.b64encode(target.read_bytes()).decode("ascii")}

async def prepare_verified_sound(film:dict,track:dict,source:Path,target:Path)->None:
    evidence=track.get("soundEvidence")
    if not isinstance(evidence,dict) or evidence.get("verifiedBy")!="gemini_audio_observation_v1" or evidence.get("actualAudioAnalysis") is not True:
        raise ValueError("Preuve sonore absente.")
    if evidence.get("match")!="pass" or evidence.get("containsSpeech") is not False or evidence.get("containsMusic") is not False:
        raise ValueError("Effet sonore non validé.")
    if evidence.get("mediaRef")!=track.get("mediaRef") or evidence.get("expectedContent")!=track.get("expectedContent") or not HASH.fullmatch(str(evidence.get("sourceSha256",""))):
        raise ValueError("Preuve sonore incohérente.")
    media=next((m for m in film.get("media",[]) if m.get("id")==track.get("mediaRef")),{})
    if not licensed_public_sound(media):raise ValueError("Licence sonore non validée.")
    if not source.is_file() or source.stat().st_size>MAX_SOUND_BYTES or await asyncio.to_thread(_hash,source)!=evidence["sourceSha256"]:
        raise ValueError("Le fichier son a changé depuis son analyse.")
    offset=0.0
    matched=False
    for scene in sorted(film.get("scenes",[]),key=lambda s:s.get("order",0)):
        for shot in scene.get("shots",[]):
            if shot.get("id")!=evidence.get("shotId"):continue
            narrative=(scene.get("narration") or {}).get("text") or scene.get("narrativeGoal")
            if not excerpt_matches(narrative,evidence.get("narrationQuote")):
                raise ValueError("La narration du son a changé.")
            quote=shot.get("visualText") if shot.get("visualMode")=="programmatic" else (shot.get("visualEvidence") or {}).get("narrationQuote")
            if not excerpt_matches(quote,evidence.get("narrationQuote")):
                raise ValueError("Le son ne correspond plus au plan.")
            start=float(evidence["offsetSec"]);duration=float(evidence["durationSec"])
            length=float(shot["outSec"])-float(shot["inSec"])
            if not math.isfinite(start+duration) or start<0 or start+duration>length+.001:
                raise ValueError("L'effet dépasse le plan vérifié.")
            await extract_audio_clip(source,float(evidence["sourceInSec"]),duration,target)
            track["events"]=[{"startSec":round(offset+float(shot["inSec"])+start,3),"durationSec":duration}]
            matched=True
            break
        if matched:break
        offset+=float(scene["durationSec"])
    if not matched:raise ValueError("Plan sonore introuvable.")

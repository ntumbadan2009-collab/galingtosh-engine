from __future__ import annotations
import re
from pathlib import Path
from typing import Any

DEFAULT_VOICES = {"fr":"fr-FR-DeniseNeural","en":"en-US-AriaNeural","es":"es-ES-ElviraNeural","pt":"pt-BR-FranciscaNeural","de":"de-DE-KatjaNeural"}

async def synthesize_tts_tracks(film: dict[str, Any], workdir: Path) -> tuple[dict[str, Path], list[str]]:
    """Synthèse vocale facultative Edge TTS sans clé API."""
    generated = {}
    warnings = []
    try:
        import edge_tts
    except ImportError:
        if any(isinstance(t,dict) and t.get("tts") for t in (film.get("audio") or {}).get("tracks",[])):
            warnings.append("TTS indisponible : dépendance edge-tts absente.")
        return generated,warnings
    for index,track in enumerate((film.get("audio") or {}).get("tracks",[])):
        if not isinstance(track,dict) or not isinstance(track.get("tts"),dict):
            continue
        spec=track["tts"]
        provider=str(spec.get("provider") or "edge-tts").lower()
        if provider!="edge-tts":
            warnings.append(f"Fournisseur TTS « {provider} » non pris en charge."); continue
        text=str(spec.get("text") or "").strip()
        if not text or len(text)>4000:
            warnings.append(f"Texte TTS invalide ou trop long pour la piste {track.get('id',index+1)}."); continue
        language=str(spec.get("language") or (film.get("info") or {}).get("language") or "fr").split("-")[0].lower()
        voice=str(spec.get("voice") or DEFAULT_VOICES.get(language,DEFAULT_VOICES["fr"]))
        if not re.fullmatch(r"[A-Za-z0-9-]{2,80}",voice):
            warnings.append(f"Voix TTS invalide pour la piste {track.get('id',index+1)}."); continue
        media_id=str(track.get("id") or f"tts-{index+1}")
        destination=workdir/f"{media_id.replace('/','_')}.tts.mp3"
        try:
            communicator=edge_tts.Communicate(text,voice)
            await communicator.save(str(destination))
            if not destination.is_file() or destination.stat().st_size==0:
                raise RuntimeError("Fichier TTS vide.")
            generated[media_id]=destination
            track["mediaRef"]=media_id
        except Exception:
            destination.unlink(missing_ok=True)
            warnings.append(f"Échec de synthèse vocale pour la piste {track.get('id',index+1)}.")
    return generated,warnings

from __future__ import annotations
import re
import asyncio
import hashlib
import logging
import os
import gc
import threading
import wave
from pathlib import Path
from typing import Any
from app.media.ffmpeg import probe_media

logger = logging.getLogger("galingtosh.tts")
PIPER_VOICE_PATH = Path(os.getenv("PIPER_VOICE_PATH", "/opt/piper/fr_FR-siwis-medium.onnx"))
_piper_voice = None
_piper_lock = threading.Lock()

DEFAULT_VOICES = {"fr":"fr-FR-DeniseNeural","en":"en-US-AriaNeural","es":"es-ES-ElviraNeural","pt":"pt-BR-FranciscaNeural","de":"de-DE-KatjaNeural"}

def _voice(language: str, voice: str | None) -> str:
    lang = (language or "fr").split("-")[0].lower()
    selected = str(voice or "default")
    # Film plans may store Google voice identifiers (for example
    # fr-FR-Neural2-B). Edge TTS does not accept those names; map them to the
    # supported language default instead of failing before Piper fallback.
    if selected == "default" or re.fullmatch(r"[a-z]{2}-[A-Z]{2}-(?:Standard|Neural2)-[A-Z]", selected):
        selected = DEFAULT_VOICES.get(lang, DEFAULT_VOICES["fr"])
    if not re.fullmatch(r"[A-Za-z0-9-]{2,80}", selected):
        raise ValueError("Voix TTS invalide.")
    return selected

def _synthesize_piper(text: str, destination: Path) -> None:
    global _piper_voice
    if not PIPER_VOICE_PATH.is_file():
        raise RuntimeError("Modèle vocal local Piper absent.")
    from piper import PiperVoice
    with _piper_lock:
        if _piper_voice is None:
            _piper_voice = PiperVoice.load(str(PIPER_VOICE_PATH))
        with wave.open(str(destination), "wb") as wav_file:
            _piper_voice.synthesize_wav(text, wav_file)


def release_piper_voice() -> None:
    """Release the ONNX model before FFmpeg renders on small instances."""
    global _piper_voice
    with _piper_lock:
        _piper_voice = None
    gc.collect()


async def synthesize_text_with_provider(
    text: str, language: str, voice: str | None, destination: Path,
    preferred_provider: str = "edge-tts",
) -> tuple[float, str]:
    """Synthesize speech, falling back to the bundled local French Piper voice."""
    clean = str(text or "").strip()
    if not clean or len(clean) > 4000:
        raise ValueError("Texte TTS invalide (1 à 4000 caractères).")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lang = (language or "fr").split("-")[0].lower()
    providers = [preferred_provider] if preferred_provider == "piper" else ["edge-tts", "piper"]
    errors = []
    for provider in providers:
        try:
            if provider == "edge-tts":
                import edge_tts
                await asyncio.wait_for(edge_tts.Communicate(clean, _voice(language, voice)).save(str(destination)), timeout=45)
            elif provider == "piper" and lang == "fr":
                await asyncio.wait_for(asyncio.to_thread(_synthesize_piper, clean, destination), timeout=90)
            else:
                raise RuntimeError(f"Aucune voix Piper locale disponible pour {lang}.")
            if not destination.is_file() or destination.stat().st_size == 0:
                raise RuntimeError("Fichier TTS vide.")
            info = await probe_media(str(destination))
            seconds = float(info.get("format", {}).get("duration", 0))
            if seconds <= 0:
                raise RuntimeError("Durée TTS impossible à mesurer.")
            return seconds, provider
        except Exception as exc:
            destination.unlink(missing_ok=True)
            logger.warning("Échec du fournisseur vocal %s (%s).", provider, type(exc).__name__)
            errors.append(type(exc).__name__)
    raise RuntimeError("Aucun fournisseur vocal disponible (" + ", ".join(errors) + ").")


async def synthesize_text(text: str, language: str, voice: str | None, destination: Path) -> float:
    """Generate one TTS segment and return its measured media duration."""
    seconds, _provider = await synthesize_text_with_provider(text, language, voice, destination)
    return seconds

async def synthesize_scene_narrations(film: dict[str, Any], workdir: Path) -> tuple[dict[str, Path], dict[str, float], list[str]]:
    """Synthesize independent narration segments, one bound to each scene."""
    files: dict[str, Path] = {}
    durations: dict[str, float] = {}
    warnings: list[str] = []
    scenes = sorted(film.get("scenes", []), key=lambda s: s.get("order", 0))
    try:
        for index, scene in enumerate(scenes, 1):
            spec = scene.get("narration") if isinstance(scene, dict) else None
            if not isinstance(spec, dict) or not str(spec.get("text") or "").strip():
                continue
            scene_id = str(scene.get("id") or index)
            media_id = f"__scene_narration_{scene_id}"
            destination = workdir / f"{hashlib.sha256(media_id.encode()).hexdigest()[:24]}.scene-tts.mp3"
            language = str(spec.get("language") or (film.get("info") or {}).get("language") or "fr")
            try:
                duration, provider = await synthesize_text_with_provider(
                    str(spec["text"]), language, spec.get("voice"), destination,
                    str(spec.get("ttsProvider") or "edge-tts"),
                )
                files[media_id] = destination
                durations[scene_id] = duration
                spec["ttsProvider"] = provider
            except Exception:
                destination.unlink(missing_ok=True)
                warnings.append(f"Narration TTS impossible à générer ou mesurer pour la scène {index}.")
    finally:
        release_piper_voice()
    return files, durations, warnings

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
        if provider not in {"edge-tts", "default"}:
            warnings.append(f"Fournisseur TTS « {provider} » non pris en charge."); continue
        text=str(spec.get("text") or "").strip()
        if not text or len(text)>4000:
            warnings.append(f"Texte TTS invalide ou trop long pour la piste {track.get('id',index+1)}."); continue
        language=str(spec.get("language") or (film.get("info") or {}).get("language") or "fr")
        media_id=str(track.get("id") or f"tts-{index+1}")
        destination=workdir/f"{hashlib.sha256(media_id.encode()).hexdigest()[:24]}.tts.mp3"
        try:
            resolved_voice = _voice(language, spec.get("voice"))
            await asyncio.wait_for(edge_tts.Communicate(text, resolved_voice).save(str(destination)), timeout=90)
            if not destination.is_file() or destination.stat().st_size == 0:
                raise RuntimeError("Fichier TTS vide.")
            generated[media_id]=destination
            track["mediaRef"]=media_id
        except Exception:
            destination.unlink(missing_ok=True)
            warnings.append(f"Échec de synthèse vocale pour la piste {track.get('id',index+1)}.")
    return generated,warnings


"""Conservative repair of inaccessible visual media; never invent replacement footage."""
from pathlib import Path
from app.core.narrative_policy import excerpt_matches, MAX_CODE_CARD_SECONDS
from app.media.ffmpeg import probe_media, FFmpegError
import math
from PIL import Image

def replace_with_grounded_card(scene: dict, shot: dict) -> bool:
    evidence = shot.get("visualEvidence") or {}
    quote = evidence.get("narrationQuote")
    narration = (scene.get("narration") or {}).get("text") or scene.get("narrativeGoal")
    length = float(shot["outSec"])-float(shot["inSec"])
    if shot.get("visualMode") == "programmatic" or not excerpt_matches(narration,quote) or not 0.25 <= length <= MAX_CODE_CARD_SECONDS:
        return False
    for key in ("mediaRef","sourceInSec","visualEvidence","visualSpec"):
        shot.pop(key,None)
    shot.update(visualMode="programmatic",visualText=quote,cardStyle="question" if "?" in quote else "focus",camera={"type":"none"})
    return True

async def repair_unavailable_media(film: dict, files: dict[str,Path]) -> list[str]:
    """Worker-local repair after voice alignment, without changing saved film or timings."""
    if (film.get("info") or {}).get("editorialLevel") not in {3, 4, 5} or (film.get("info") or {}).get("visualPolicy") != "strict":
        return []
    media = {m.get("id"):m for m in film.get("media",[])}
    warnings=[]
    durations={}
    valid_images={}
    for scene in film.get("scenes",[]):
        for shot in scene.get("shots",[]):
            ref=shot.get("mediaRef")
            if not ref: continue
            path=files.get(ref)
            reason=None
            if not path or not path.is_file():
                reason="média indisponible"
            elif media.get(ref,{}).get("kind")=="video":
                if ref not in durations:
                    try:
                        p=await probe_media(str(path))
                        durations[ref]=float(p.get("format",{}).get("duration",0)) if any(s.get("codec_type")=="video" for s in p.get("streams",[])) else 0
                    except (FFmpegError,ValueError,TypeError):
                        durations[ref]=0
                end=float(shot.get("sourceInSec",0))+float(shot["outSec"])-float(shot["inSec"])
                if not math.isfinite(durations[ref]) or end>durations[ref]+.06:
                    reason="séquence source trop courte ou illisible"
            elif media.get(ref,{}).get("kind") == "image":
                if ref not in valid_images:
                    try:
                        with Image.open(path) as im:
                            im.verify()
                        valid_images[ref]=True
                    except (OSError, ValueError, Image.DecompressionBombError):
                        valid_images[ref]=False
                if not valid_images[ref]:
                    reason="image source corrompue"
            if reason and replace_with_grounded_card(scene,shot):
                warnings.append(f"Plan {shot.get('id')}: {reason}; remplacé par une citation fidèle, durée conservée.")
    return warnings

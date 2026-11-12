from typing import Any

ASPECTS = {"16:9", "9:16", "1:1", "4:3", "4:5", "21:9", "custom"}
CAMERAS = {"ken_burns", "dolly", "pan", "tilt", "zoom_in", "zoom_out", "none"}
TRANSITIONS = {"cut", "dissolve", "fade", "slide", "zoom", "wipe"}
EFFECTS = {"fade_in", "fade_out", "grayscale", "vignette", "text_overlay"}

def validate_film(film: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(film, dict):
        return {"valid": False, "errors": ["Le document Film doit être un objet JSON."], "warnings": []}
    fmt = film.get("format") or {}
    if fmt.get("aspect") not in ASPECTS:
        errors.append("format.aspect est absent ou invalide.")
    if fmt.get("aspect") == "custom":
        w, h = fmt.get("width"), fmt.get("height")
        if not isinstance(w, int) or not isinstance(h, int) or w < 2 or h < 2:
            errors.append("Le format custom exige width et height entiers supérieurs ou égaux à 2.")
    fps = fmt.get("fps", 24)
    if not isinstance(fps, (int, float)) or fps <= 0 or fps > 60:
        errors.append("format.fps doit être compris entre 0 et 60.")
    scenes = film.get("scenes", [])
    if not isinstance(scenes, list):
        errors.append("scenes doit être un tableau.")
        scenes = []
    if not scenes:
        warnings.append("Aucune scène : le rendu ne contiendra pas de séquence.")
    shot_ids: set[str] = set()
    for si, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            errors.append(f"scenes[{si}] doit être un objet.")
            continue
        duration = scene.get("durationSec", 0)
        if not isinstance(duration, (int, float)) or duration <= 0:
            errors.append(f"scenes[{si}].durationSec doit être positif.")
        shots = scene.get("shots", [])
        if not isinstance(shots, list):
            errors.append(f"scenes[{si}].shots doit être un tableau.")
            continue
        if not shots:
            warnings.append(f"Scène {si + 1} sans plan : fond neutre prévu.")
        for pi, shot in enumerate(shots):
            if not isinstance(shot, dict):
                errors.append(f"Plan {si + 1}.{pi + 1} invalide.")
                continue
            sid = shot.get("id")
            if sid is not None:
                if sid in shot_ids:
                    errors.append(f"Identifiant de plan dupliqué : {sid}.")
                shot_ids.add(sid)
            start, end = shot.get("inSec", 0), shot.get("outSec", 0)
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start < 0 or end <= start:
                errors.append(f"Plan {si + 1}.{pi + 1} : inSec/outSec invalides.")
            if isinstance(duration, (int, float)) and isinstance(end, (int, float)) and end > duration:
                warnings.append(f"Plan {si + 1}.{pi + 1} dépasse la durée de sa scène et sera tronqué.")
            camera = (shot.get("camera") or {}).get("type", "none")
            if camera not in CAMERAS:
                warnings.append(f"Caméra « {camera} » non prise en charge : aucun mouvement appliqué.")
            if not shot.get("mediaRef"):
                warnings.append(f"Plan {si + 1}.{pi + 1} sans média : fond noir/neutre.")
    for tr in film.get("transitions", []) or []:
        if isinstance(tr, dict) and tr.get("type", "cut") not in TRANSITIONS:
            warnings.append(f"Transition inconnue « {tr.get('type')} » : coupe franche prévue.")
    for effect in film.get("effects", []) or []:
        if isinstance(effect, dict) and effect.get("type") not in EFFECTS:
            warnings.append(f"Effet non pris en charge « {effect.get('type')} » : ignoré.")
    for media in film.get("media", []) or []:
        if isinstance(media, dict) and media.get("kind") == "model3d":
            warnings.append("Média 3D non pris en charge dans cette version.")
    return {"valid": not errors, "errors": errors, "warnings": list(dict.fromkeys(warnings))}

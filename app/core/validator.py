from __future__ import annotations
import math
from typing import Any

ASPECTS={"16:9","9:16","1:1","4:3","4:5","21:9","custom"}
CAMERAS={"ken_burns","dolly","pan","tilt","zoom_in","zoom_out","none"}
TRANSITIONS={"cut","dissolve","fade","slide","zoom","wipe"}
EFFECTS={"fade_in","fade_out","grayscale","vignette","text_overlay"}
MEDIA_KINDS={"image","video","audio","svg","chart","animation","model3d"}

def _finite_number(value: Any) -> bool:
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(float(value))

def validate_film(film: dict[str,Any]) -> dict[str,Any]:
    errors=[]; warnings=[]
    if not isinstance(film,dict):
        return {"valid":False,"errors":["Le document Film doit être un objet JSON."],"warnings":[]}
    info=film.get("info") or {}
    if not isinstance(info,dict):
        errors.append("info doit être un objet.")
    fmt=film.get("format") or {}
    if not isinstance(fmt,dict):
        errors.append("format doit être un objet."); fmt={}
    aspect=fmt.get("aspect")
    if aspect not in ASPECTS: errors.append("format.aspect est absent ou invalide.")
    if aspect=="custom":
        w,h=fmt.get("width"),fmt.get("height")
        if not isinstance(w,int) or isinstance(w,bool) or not isinstance(h,int) or isinstance(h,bool) or w<2 or h<2 or w>7680 or h>7680:
            errors.append("Le format custom exige width et height entiers entre 2 et 7680.")
    fps=fmt.get("fps",24)
    if not _finite_number(fps) or fps<=0 or fps>60: errors.append("format.fps doit être compris entre 0 et 60.")
    scenes=film.get("scenes",[])
    if not isinstance(scenes,list):
        errors.append("scenes doit être un tableau."); scenes=[]
    if not scenes: errors.append("Le Film JSON doit contenir au moins une scène.")
    shot_ids=set()
    for si,scene in enumerate(scenes):
        if not isinstance(scene,dict):
            errors.append(f"scenes[{si}] doit être un objet."); continue
        order=scene.get("order",0)
        if not isinstance(order,(int,float)) or isinstance(order,bool) or not _finite_number(order):
            errors.append(f"scenes[{si}].order doit être numérique.")
        duration=scene.get("durationSec",0)
        if not _finite_number(duration) or duration<=0:
            errors.append(f"scenes[{si}].durationSec doit être positif et fini.")
        shots=scene.get("shots",[])
        if not isinstance(shots,list):
            errors.append(f"scenes[{si}].shots doit être un tableau."); continue
        if not shots: warnings.append(f"Scène {si+1} sans plan : fond noir prévu.")
        for pi,shot in enumerate(shots):
            if not isinstance(shot,dict):
                errors.append(f"Plan {si+1}.{pi+1} invalide."); continue
            order=shot.get("order",0)
            if not isinstance(order,(int,float)) or isinstance(order,bool) or not _finite_number(order):
                errors.append(f"Ordre du plan {si+1}.{pi+1} invalide.")
            sid=shot.get("id")
            if sid is not None:
                if not isinstance(sid,(str,int)) or isinstance(sid,bool):
                    errors.append(f"Identifiant de plan {si+1}.{pi+1} invalide.")
                elif str(sid) in shot_ids: errors.append(f"Identifiant de plan dupliqué : {sid}.")
                else: shot_ids.add(str(sid))
            start,end=shot.get("inSec",0),shot.get("outSec",0)
            if not _finite_number(start) or not _finite_number(end) or start<0 or end<=start:
                errors.append(f"Plan {si+1}.{pi+1} : inSec/outSec invalides.")
            elif _finite_number(duration):
                if end>duration: warnings.append(f"Plan {si+1}.{pi+1} dépasse la durée de sa scène et sera tronqué.")
            media_ref=shot.get("mediaRef")
            if media_ref is not None and not isinstance(media_ref,str):
                errors.append(f"Référence média du plan {si+1}.{pi+1} invalide.")
            camera=shot.get("camera") or {}
            if not isinstance(camera,dict):
                errors.append(f"Caméra du plan {si+1}.{pi+1} invalide."); camera={}
            if camera.get("type","none") not in CAMERAS:
                warnings.append(f"Caméra inconnue au plan {si+1}.{pi+1} : aucun mouvement appliqué.")
            if not shot.get("mediaRef"): warnings.append(f"Plan {si+1}.{pi+1} sans média : fond noir/neutre.")
    for section,name,allowed in [(film.get("transitions",[]) or [],"transition",TRANSITIONS),(film.get("effects",[]) or [],"effet",EFFECTS)]:
        if not isinstance(section,list):
            errors.append(f"{name}s doit être un tableau."); continue
        for item in section:
            if isinstance(item,dict) and item.get("type") not in allowed:
                warnings.append(f"{name.capitalize()} non pris en charge : ignoré.")
    media=film.get("media",[]) or []
    if not isinstance(media,list): errors.append("media doit être un tableau."); media=[]
    media_ids=set()
    for item in media:
        if not isinstance(item,dict): errors.append("Chaque média doit être un objet."); continue
        mid=item.get("id")
        if not isinstance(mid,(str,int)) or isinstance(mid,bool): errors.append("Un média possède un identifiant invalide.")
        elif str(mid) in media_ids: errors.append(f"Identifiant de média dupliqué : {mid}.")
        else: media_ids.add(str(mid))
        if item.get("kind") not in MEDIA_KINDS: warnings.append(f"Type de média non reconnu : {item.get('kind')}.")
        if item.get("kind")=="model3d": warnings.append("Média 3D non pris en charge dans cette version.")
    audio=film.get("audio") or {}
    if not isinstance(audio,dict): errors.append("audio doit être un objet."); audio={}
    tracks=audio.get("tracks",[]) or []
    if not isinstance(tracks,list): errors.append("audio.tracks doit être un tableau."); tracks=[]
    for ti,track in enumerate(tracks):
        if not isinstance(track,dict): errors.append(f"Piste audio {ti+1} invalide."); continue
        events=track.get("events",[]) or []
        if not isinstance(events,list): errors.append(f"Événements audio de la piste {ti+1} invalides."); continue
        for ei,event in enumerate(events):
            if not isinstance(event,dict) or not _finite_number(event.get("startSec",0)) or not _finite_number(event.get("durationSec",0)) or event.get("startSec",0)<0 or event.get("durationSec",0)<=0:
                errors.append(f"Événement audio {ti+1}.{ei+1} invalide.")
    subtitles=film.get("subtitles",[]) or []
    if not isinstance(subtitles,list): errors.append("subtitles doit être un tableau."); subtitles=[]
    for si,track in enumerate(subtitles):
        if not isinstance(track,dict) or not isinstance(track.get("cues",[]),list):
            errors.append(f"Piste de sous-titres {si+1} invalide."); continue
        for ci,cue in enumerate(track.get("cues",[])):
            if not isinstance(cue,dict) or not _finite_number(cue.get("startSec")) or not _finite_number(cue.get("endSec")) or cue.get("startSec",0)<0 or cue.get("endSec",0)<=cue.get("startSec",0):
                errors.append(f"Repère de sous-titre {si+1}.{ci+1} invalide.")
    render=film.get("render") or {}
    if not isinstance(render,dict):
        errors.append("render doit être un objet.")
    elif render.get("resolution","720p") not in {"720p","1080p","4k"}:
        errors.append("render.resolution doit être 720p, 1080p ou 4k.")
    if isinstance(render,dict) and "audioBitrateKbps" in render:
        bitrate=render["audioBitrateKbps"]
        if not isinstance(bitrate,int) or isinstance(bitrate,bool) or not 64<=bitrate<=256:
            errors.append("render.audioBitrateKbps doit être un entier entre 64 et 256.")
    return {"valid":not errors,"errors":errors,"warnings":list(dict.fromkeys(warnings))}

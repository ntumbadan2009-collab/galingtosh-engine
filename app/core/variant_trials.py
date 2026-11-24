"""Experimental isolated A/B scene renders, never mutate a film or queue a job.

Requires two pre-validated local scene films, identical narration, timing,
audio, subtitles and source inventory. No user-supplied executable code.
A trial is evidence for an artistic decision, not itself a decision.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
from app.core.renderer import FilmRenderer
from app.core.narrative_policy import narrative_issues
from app.core.editorial import timeline_issues
from app.core.cinematic_review import collect_review_batches

VISUAL_FIELDS={"visualMode","visualText","visualSpec","visualEvidence","mediaRef","sourceInSec","camera","cardStyle"}

def _quote(sh:dict):
    return sh.get("visualText") if sh.get("visualMode")=="programmatic" else (sh.get("visualEvidence") or {}).get("narrationQuote")

def _fingerprint(film:dict):
    fixed=copy.deepcopy(film)
    for sh in fixed["scenes"][0]["shots"]:
        for key in VISUAL_FIELDS:sh.pop(key,None)
    return fixed

def validate_trial(a:dict,b:dict)->None:
    for f in (a,b):
        if (f.get("info") or {}).get("editorialLevel")!=5 or (f.get("info") or {}).get("visualPolicy")!="strict":
            raise ValueError("Comparaison réservée aux films stricts de niveau 5.")
        scenes=f.get("scenes",[])
        if len(scenes)!=1 or not 1<=len(scenes[0].get("shots",[]))<=4:
            raise ValueError("Essai limité à une scène et quatre plans.")
        d=float(scenes[0]["durationSec"])
        if not math.isfinite(d) or not 1<=d<=24:
            raise ValueError("Essai limité à 24 secondes.")
        if narrative_issues(f) or timeline_issues(f):
            raise ValueError("Variante sans preuve narrative ou minutage valide.")
        if (f.get("render") or {}).get("resolution","720p")!="720p":
            raise ValueError("Essai limité à 720p.")
    if _fingerprint(a)!=_fingerprint(b):
        raise ValueError("Les variantes doivent conserver narration, durée, audio, sous-titres et inventaire.")
    for sa,sb in zip(a["scenes"][0]["shots"],b["scenes"][0]["shots"]):
        if _quote(sa)!=_quote(sb):
            raise ValueError("Les variantes doivent illustrer les mêmes extraits.")
    if a==b:
        raise ValueError("Deux variantes identiques ne constituent pas un essai.")

async def render_trial(a:dict,b:dict,media_files:dict[str,Path],directory:Path)->dict:
    validate_trial(a,b)
    directory.mkdir(parents=True,exist_ok=False)
    results=[]
    for label,film in (("A",a),("B",b)):
        output=directory/f"{label}.mp4"
        local=copy.deepcopy(film)
        report=await FilmRenderer(max_seconds=24,max_output_mb=20).render(local,dict(media_files),output)
        if not report["editorial_quality"]["passed"]:
            raise ValueError("Échec technique de variante.")
        batches=await collect_review_batches(output,local,directory/f"{label}_evidence")
        with output.open("rb") as stream:sha=hashlib.file_digest(stream,"sha256").hexdigest()
        results.append({"id":label,"sha256":sha,"report":report,"batches":[{"index":x["index"],"count":x["count"],"file":str(x["path"].relative_to(directory))} for x in batches]})
    result={"version":1,"candidates":results,"status":"needs_artistic_review",
            "winner":None,"limitations":"Rendus réels et images échantillonnées; aucune écoute sémantique ni mesure de rétention. Aucune publication automatique."}
    (directory/"comparison.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result

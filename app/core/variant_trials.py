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
import base64
import io
from PIL import Image, ImageDraw, ImageFont
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

def paired_evidence(directory:Path,candidates:list[dict])->list[dict]:
    """Each contact sheet shows the same shots/time samples, both alternatives."""
    if len(candidates)!=2 or len(candidates[0]["batches"])!=len(candidates[1]["batches"]):
        raise ValueError("Couverture comparative incomplète.")
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",20)
    results=[]
    for x,y in zip(candidates[0]["batches"],candidates[1]["batches"]):
        pa=json.loads((directory/x["file"]).read_text())
        pb=json.loads((directory/y["file"]).read_text())
        if pa["shots"]!=pb["shots"] or pa["index"]!=pb["index"]:
            raise ValueError("Les images de comparaison ne couvrent pas le même passage.")
        with Image.open(io.BytesIO(base64.b64decode(pa["jpegBase64"]))) as a, Image.open(io.BytesIO(base64.b64decode(pb["jpegBase64"]))) as b:
            if a.size!=b.size:raise ValueError("Dimensions comparatives incohérentes.")
            # A above B, each row contains the two sampled times of one shot.
            canvas=Image.new("RGB",(a.width,2*(a.height+32)),(18,22,30))
            d=ImageDraw.Draw(canvas)
            d.text((10,3),"VARIANTE A",font=font,fill="white")
            canvas.paste(a,(0,32))
            d.text((10,a.height+35),"VARIANTE B",font=font,fill="white")
            canvas.paste(b,(0,a.height+64))
            buf=io.BytesIO();canvas.save(buf,"JPEG",quality=82,optimize=True);canvas.close()
        jpeg=buf.getvalue()
        if len(jpeg)>500000:raise ValueError("Preuve comparative trop volumineuse.")
        payload={"version":1,"index":pa["index"],"shots":pa["shots"],
                 "candidateHashes":{c["id"]:c["sha256"] for c in candidates},
                 "jpegBase64":base64.b64encode(jpeg).decode("ascii")}
        path=directory/f"paired_{pa['index']:03d}.json"
        path.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        results.append({"index":pa["index"],"count":len(pa["shots"]),"file":path.name,
                        "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    return results

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
    result={"version":1,"candidates":results,"pairedEvidence":paired_evidence(directory,results),"status":"needs_artistic_review",
            "winner":None,"limitations":"Rendus réels et images échantillonnées; aucune écoute sémantique ni mesure de rétention. Aucune publication automatique."}
    (directory/"comparison.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result

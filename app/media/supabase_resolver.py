from __future__ import annotations
import json
import asyncio
from pathlib import Path
from typing import Any
from app.media.resolver import download_public_media
from app.media.secure_web import is_extended,download_extended,clean_image,digest
from app.media.audio_evidence import licensed_public_sound, MAX_SOUND_BYTES
from app.media.graphics import chart_to_png, chart_to_video, sanitize_svg_to_png
from app.storage.supabase import SupabaseREST, SupabaseError

MAX_MEDIA_BYTES = 200 * 1024 * 1024
ALLOWED_MIME = {
 "image":{"image/jpeg","image/png","image/webp","image/gif","image/bmp","image/svg+xml"},
 "video":{"video/mp4","video/quicktime","video/webm","video/x-matroska"},
 "audio":{"audio/mpeg","audio/mp4","audio/wav","audio/x-wav","audio/ogg","audio/aac","audio/flac"},
 "svg":{"image/svg+xml"},"chart":{"application/json"}}
EXTENSIONS = {"image/jpeg":".jpg","image/png":".png","image/webp":".webp","image/gif":".gif","image/bmp":".bmp",
 "image/svg+xml":".svg","video/mp4":".mp4","video/quicktime":".mov","video/webm":".webm","video/x-matroska":".mkv",
 "audio/mpeg":".mp3","audio/mp4":".m4a","audio/wav":".wav","audio/x-wav":".wav","audio/ogg":".ogg","audio/aac":".aac","audio/flac":".flac"}

def _media_ids(film:dict[str,Any])->list[str]:
 used={str(s["mediaRef"]) for scene in film.get("scenes",[]) for s in scene.get("shots",[]) if s.get("mediaRef")}
 used.update(str(t["mediaRef"]) for t in (film.get("audio") or {}).get("tracks",[]) if t.get("mediaRef") and not t.get("disabled"))
 return [str(m["id"]) for m in film.get("media",[]) if isinstance(m,dict) and m.get("id") and str(m["id"]) in used]

def _credit(row:dict)->dict:
 p=row.get("provenance") or {}
 return {"media_id":row.get("id"),"author":p.get("author") or "Auteur non renseigné",
 "source":p.get("source") or p.get("title") or "Source non renseignée",
 "license":p.get("license") or row.get("license") or "Licence non renseignée",
 "license_url":p.get("license_url"),"url":p.get("url"),"attribution":p.get("attribution"),
 "restrictions":p.get("restrictions") or []}

async def resolve_film_media(film:dict[str,Any],project_id:str,user_id:str,db:SupabaseREST,workdir:Path):
 needed=set(_media_ids(film))
 rows=await db.read_media_assets(project_id,list(needed)) if needed else []
 by_id={str(row.get("id")):row for row in rows}
 files={}; warnings=[]; credits=[]
 for index,item in enumerate(film.get("media",[])):
  if not isinstance(item,dict) or not item.get("id"): continue
  mid=str(item["id"])
  if mid not in needed: continue
  row=by_id.get(mid)
  if not row or str(row.get("user_id"))!=user_id: warnings.append(f"Média {mid} absent ou hors périmètre : ignoré."); continue
  checked_sound=any(t.get("soundEvidence") and t.get("mediaRef")==mid for t in (film.get("audio") or {}).get("tracks",[]) if isinstance(t,dict))
  if checked_sound and not licensed_public_sound(row):warnings.append(f"Licence sonore de {mid} non conforme.");continue
  kind=str(row.get("kind") or "").lower(); source=str(row.get("source") or "")
  if kind=="model3d": warnings.append(f"Média 3D {mid} non pris en charge."); continue
  if kind not in ALLOWED_MIME: warnings.append(f"Type de média {mid} non pris en charge."); continue
  target=workdir/f"asset_{index:04d}"
  try:
   if kind=="chart" and source=="generated_programmatic":
    spec=row.get("storage_path")
    if isinstance(spec,str): spec=json.loads(spec)
    if not isinstance(spec,dict): raise SupabaseError("Spécification de graphique invalide.")
    animate=bool(spec.get("animated"))
    if animate:
     uses=[float(shot.get("outSec",0))-float(shot.get("inSec",0)) for scene in film.get("scenes",[]) for shot in scene.get("shots",[]) if str(shot.get("mediaRef"))==mid]
     duration=max(uses,default=0)
     if duration<=0: raise SupabaseError("Graphique animé sans plan associé ou durée exploitable.")
     final=target.with_suffix(".mp4"); chart_to_video(spec,final,duration,int((film.get("format") or {}).get("fps",24)))
    else:
     final=target.with_suffix(".png"); chart_to_png(spec,final)
    files[mid]=final; continue
   if source=="upload":
    _,mime=await db.download_user_upload(str(row.get("storage_path") or ""),user_id,target,MAX_MEDIA_BYTES)
   elif source=="search":
    provenance=row.get("provenance") or {}
    url=provenance.get("download_url") or provenance.get("preview_url")
    if not url: warnings.append(f"Média recherché {mid} sans URL."); continue
    if is_extended(row):
     uses=[shot for scene in film.get("scenes",[]) for shot in scene.get("shots",[]) if shot.get("mediaRef")==mid]
     if not uses: continue
     _,mime=await download_extended(row,target)
     sha=await asyncio.to_thread(digest,target)
     if any((shot.get("visualEvidence") or {}).get("assetSha256")!=sha or (shot.get("visualEvidence") or {}).get("contentSafetyChecked") is not True for shot in uses):
      raise SupabaseError("Le fichier Web a changé ou ne dispose pas de preuve de sécurité.")
     if kind=="image":
      final=target.with_suffix(".jpg")
      await asyncio.to_thread(clean_image,target,final)
      target.unlink(missing_ok=True)
      files[mid]=final;credits.append(_credit(row));continue
    else:
     _,mime=await download_public_media(str(url),target,MAX_SOUND_BYTES if checked_sound else MAX_MEDIA_BYTES)
   else:
    warnings.append(f"Source « {source} » du média {mid} non prise en charge."); continue
   if kind=="image":
    expected={str((shot.get("visualEvidence") or {}).get("assetSha256")) for scene in film.get("scenes",[]) for shot in scene.get("shots",[]) if shot.get("mediaRef")==mid and (shot.get("visualEvidence") or {}).get("assetSha256")}
    if expected and expected!={await asyncio.to_thread(digest,target)}:
     raise SupabaseError("Le fichier image a changé depuis son contrôle visuel.")
   if mime not in ALLOWED_MIME[kind]: raise SupabaseError("Type MIME incompatible.")
   if kind=="svg" or mime=="image/svg+xml":
    final=target.with_suffix(".png"); sanitize_svg_to_png(target,final); target.unlink(missing_ok=True)
   else:
    final=target.with_suffix(EXTENSIONS[mime]); target.replace(final)
   files[mid]=final
   if source=="search":
    credit=_credit(row)
    credits.append(credit)
    if credit["license"]=="Licence non renseignée" or not credit.get("attribution"):
     warnings.append(f"Crédits incomplets pour le média recherché {mid} : vérifiez la licence et l’attribution.")
  except Exception:
   target.unlink(missing_ok=True); warnings.append(f"Média {mid} indisponible ou non conforme : ignoré.")
 return files,list(dict.fromkeys(warnings)),credits

def write_credits(path:Path,credits:list[dict])->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(credits,ensure_ascii=False,indent=2),encoding="utf-8")

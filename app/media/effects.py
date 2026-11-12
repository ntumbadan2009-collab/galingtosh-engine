from __future__ import annotations
import math
from pathlib import Path
from typing import Any
from app.media.ffmpeg import run_ffmpeg

_ALLOWED={"fade_in","fade_out","grayscale","vignette","text_overlay"}

def _escape_drawtext(value:str)->str:
    return value.replace("\\","\\\\").replace(":","\\:").replace("'","\\'").replace("%","\\%").replace(",","\\,").replace("\n"," ")

def build_video_filters(effects:list[dict[str,Any]],duration:float,width:int,height:int)->tuple[list[str],list[str]]:
    filters=[]; warnings=[]
    for effect in effects:
        if not isinstance(effect,dict): continue
        kind=str(effect.get("type",""))
        if kind not in _ALLOWED:
            warnings.append(f"Effet « {kind} » non pris en charge : ignoré."); continue
        params=effect.get("params") or {}
        if not isinstance(params,dict):
            warnings.append(f"Paramètres invalides pour l’effet « {kind} » : ignoré."); continue
        try:
            if kind=="grayscale": filters.append("hue=s=0")
            elif kind=="vignette": filters.append("vignette=PI/5")
            elif kind in {"fade_in","fade_out"}:
                seconds=float(params.get("durationSec",1))
                if not math.isfinite(seconds): raise ValueError
                seconds=max(0.05,min(5.0,seconds))
                if kind=="fade_in": filters.append(f"fade=t=in:st=0:d={seconds:.3f}")
                else: filters.append(f"fade=t=out:st={max(0.0,duration-seconds):.3f}:d={seconds:.3f}")
            elif kind=="text_overlay":
                text=_escape_drawtext(str(params.get("text",""))[:300])
                if text:
                    size=int(params.get("fontSize",max(24,width//28)))
                    size=max(12,min(96,size))
                    position=str(params.get("position","bottom")).lower()
                    y="h-th-2*text_h" if position=="top" or position=="bottom" else "(h-text_h)/2"
                    filters.append(f"drawtext=text='{text}':fontcolor=white:fontsize={size}:borderw=2:bordercolor=black:x=(w-text_w)/2:y={y}")
        except (TypeError,ValueError,OverflowError):
            warnings.append(f"Paramètres invalides pour l’effet « {kind} » : ignoré.")
    return filters,warnings

async def finish_video(source:Path,destination:Path,filters:list[str],subtitle_file:Path|None=None)->None:
    applied=list(filters)
    if subtitle_file and subtitle_file.is_file():
        path=str(subtitle_file.resolve()).replace("\\","/").replace(":","\\:")
        applied.append(f"subtitles='{path}':force_style='FontName=DejaVu Sans,FontSize=24,Outline=2,Shadow=1,MarginV=36'")
    if not applied:
        source.replace(destination); return
    await run_ffmpeg(["-i",str(source),"-vf",",".join(applied),"-map","0:v:0","-map","0:a?",
        "-c:v","libx264","-preset","veryfast","-threads","1","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","128k","-movflags","+faststart",str(destination)])

from __future__ import annotations
import math
from pathlib import Path
from typing import Any
from PIL import ImageFont

def _timestamp(seconds:float)->str:
    milliseconds=max(0,round(seconds*1000))
    hours,milliseconds=divmod(milliseconds,3600000)
    minutes,milliseconds=divmod(milliseconds,60000)
    secs,milliseconds=divmod(milliseconds,1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"

def subtitle_font_size(width:int,height:int)->int:
    # libass uses the default SRT PlayResY=288.
    return 18 if width>=height else 12

def _caption_chunks(text:str,width:int=1280,height:int=720)->list[str]:
    """Two measured-width lines maximum. Every word survives segmentation."""
    px=max(12,round(subtitle_font_size(width,height)*height/288))
    try:font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",px)
    except OSError:font=ImageFont.load_default(size=px)
    max_width=width*.82
    rows=[];line=""
    for word in text.split():
        if font.getlength(word)>max_width:
            raise ValueError("Sous-titre : mot trop long pour rester lisible.")
        proposed=(line+" "+word).strip()
        if line and font.getlength(proposed)>max_width:
            rows.append(line);line=word
        else:line=proposed
    if line:rows.append(line)
    return ["\n".join(rows[i:i+2]) for i in range(0,len(rows),2)]

def write_srt(subtitles:list[dict[str,Any]],destination:Path,language:str|None=None,*,width:int=1280,height:int=720)->bool:
    selected=next((s for s in subtitles if language and s.get("language")==language),None)
    selected=selected or (subtitles[0] if subtitles else None)
    if not selected:return False
    cues=selected.get("cues") or []
    lines=[];valid=0
    for cue in cues:
        try:
            start,end=float(cue.get("startSec",0)),float(cue.get("endSec",0))
            content=str(cue.get("text","")).strip()
        except (TypeError,ValueError):continue
        if not content or not math.isfinite(start+end) or start<0 or end<=start:continue
        parts=_caption_chunks(content,width,height)
        weights=[max(1,len(part)) for part in parts]
        total=sum(weights);cursor=start
        for index,(part,weight) in enumerate(zip(parts,weights)):
            part_end=end if index==len(parts)-1 else cursor+(end-start)*weight/total
            if round(part_end*1000)<=round(cursor*1000):
                raise ValueError("Sous-titre : durée trop courte.")
            valid+=1
            lines.extend([str(valid),f"{_timestamp(cursor)} --> {_timestamp(part_end)}",part,""])
            cursor=part_end
    if not valid:return False
    destination.write_text("\n".join(lines),encoding="utf-8-sig")
    return True

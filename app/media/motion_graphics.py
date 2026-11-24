"""Narration-grounded motion diagrams rendered entirely by Python + FFmpeg.

No AI media generation, no arbitrary statistics and no remote visual assets.
Cards reveal *verbatim* fragments of a single approved narration excerpt.
The stage animation is an editorial rhythm, not forced word-level alignment.
"""
from __future__ import annotations

import asyncio
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.media.ffmpeg import run_ffmpeg
from app.media.geometry3d import draw_geometry

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
VISUAL_TYPES = {"focus", "steps", "timeline", "comparison", "cause_effect", "cube_rotation", "sphere_rotation"}
PALETTE = {
    "focus": ((10, 23, 42), (108, 229, 201)),
    "steps": ((12, 29, 44), (104, 205, 250)),
    "timeline": ((23, 23, 47), (192, 153, 255)),
    "comparison": ((33, 23, 40), (251, 170, 123)),
    "cause_effect": ((13, 35, 38), (95, 231, 195)),
    "cube_rotation": ((14, 24, 43), (122, 219, 249)),
    "sphere_rotation": ((14, 24, 43), (122, 219, 249)),
}
FRAME_RATE = 8


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT, max(12, size))
    except OSError:
        return ImageFont.load_default(size=max(12, size))


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float):
    return tuple(round(x+(y-x)*max(0.0,min(1.0,t))) for x,y in zip(a,b))


def _ease(t: float) -> float:
    t=max(0.0,min(1.0,t))
    return t*t*(3-2*t)


def _rounded(draw: ImageDraw.ImageDraw, box, radius: int, **kwargs):
    x0,y0,x1,y1=[int(z) for z in box]
    if x1<=x0 or y1<=y0: return
    draw.rounded_rectangle((x0,y0,x1,y1),radius=max(1,min(radius,(x1-x0)//3,(y1-y0)//3)),**kwargs)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int):
    lines=[]
    for part in text.split("\n"):
        row=""
        for word in part.split():
            candidate=(row+" "+word).strip()
            if row and draw.textbbox((0,0),candidate,font=font)[2] > max_width:
                lines.append(row);row=word
            else: row=candidate
        if row:lines.append(row)
    return lines or [""]


def _fitted(draw: ImageDraw.ImageDraw, text: str, box, *, strong: bool, tint):
    x0,y0,x1,y1=[int(v) for v in box]
    w,h=x1-x0,y1-y0
    if w<=0 or h<=0:return
    # Reject unreadably small text instead of silently truncating it.
    max_size=max(16,min(int(w*.09),int(h*.32),56))
    minimum=max(14,min(21,round(min(w,h)*.045)))
    for px in range(max_size,minimum-1,-2):
        f=_font(px,strong);lines=_wrap(draw,text,f,w)
        line_h=max(px+6,int(px*1.28))
        if len(lines)*line_h <= h and all(draw.textbbox((0,0),line,font=f)[2]<=w for line in lines):
            break
    else:
        raise ValueError("Texte de schéma trop long pour rester lisible.")
    y=y0+max(0,(h-len(lines)*line_h)//2)
    for line in lines:
        draw.text((x0,y),line,font=f,fill=tint)
        y+=line_h


def _layout_boxes(width: int, height: int, kind: str, count: int):
    p=max(28,round(width*.055))
    header=max(108,round(height*.20))
    footer=max(44,round(height*.11))
    top=header+round(height*.06)
    bottom=height-footer
    gap=max(14,round(min(width,height)*.025))
    portrait=height>width
    vertical=portrait or (kind=="timeline" and count>3)
    if kind=="focus":
        return [(p, top, width-p, bottom)]
    if kind=="comparison" and not portrait:
        count=2
    if vertical:
        span=(bottom-top-(count-1)*gap)/count
        return [(p,round(top+i*(span+gap)),width-p,round(top+i*(span+gap)+span)) for i in range(count)]
    span=(width-2*p-(count-1)*gap)/count
    return [(round(p+i*(span+gap)),top,round(p+i*(span+gap)+span),bottom) for i in range(count)]


def _draw_frame(*, width:int,height:int,kind:str,items:list[dict],scene_title:str,
                scene_number:int,time_sec:float,duration:float) -> Image.Image:
    bg,accent=PALETTE[kind]
    im=Image.new("RGB",(width,height),bg)
    d=ImageDraw.Draw(im)
    unit=min(width/1280,height/720) if width>=height else min(width/720,height/1280)
    margin=max(26,round(width*.055))
    # Quiet editorial background; does not depict fictitious events.
    fine=_mix(bg,(255,255,255),.042)
    step=max(28,int(72*unit))
    for x in range(0,width,step):d.line((x,0,x,height),fill=fine,width=1)
    for y in range(0,height,step):d.line((0,y,width,y),fill=fine,width=1)
    def label(text,x,y,size,color,bold=False):
        d.text((x,y),str(text),font=_font(size,bold),fill=color)
    title_h=max(100,int(height*.19))
    mark=max(5,round(8*unit))
    _rounded(d,(margin,round(title_h*.30),margin+mark,round(title_h*.73)),mark,fill=accent)
    label(f"SCÈNE {max(1,int(scene_number)):02d}",margin+mark+round(18*unit),round(title_h*.22),
          max(15,round(24*unit)),accent,True)
    title=(scene_title or "Récit visuel").strip()[:64]
    _fitted(d,title,(margin+mark+round(18*unit),round(title_h*.48),width-margin,round(title_h*.87)),
            strong=False,tint=(214,222,237))
    if kind in {"cube_rotation","sphere_rotation"}:
        top=title_h+round(height*.025)
        bottom=round(height*.70)
        draw_geometry(d,kind,(margin,top,width-margin,bottom),time_sec,duration,accent)
        _fitted(d,str(items[0]["text"]),(margin,round(height*.72),width-margin,round(height*.89)),strong=True,tint=(250,251,253))
        label("SCHÉMA GÉOMÉTRIQUE — NON À L'ÉCHELLE",margin,round(height*.93),max(12,round(15*unit)),accent,False)
        return im
    boxes=_layout_boxes(width,height,kind,len(items))
    count=len(items)
    for i,(item,box) in enumerate(zip(items,boxes)):
        x0,y0,x1,y1=box
        # First item appears immediately. Subsequent revelations follow the
        # structure of narration, with a smooth ~0.5 sec fade.
        reveal=(i/count)*duration*.76
        fade=_ease((time_sec-reveal+.18)/.52)
        if fade<=0:continue
        muted=_mix(bg,(44,62,84),fade*.8)
        border=_mix(bg,accent,fade*.85)
        panel=_mix(bg,(31,46,68),fade*.88)
        _rounded(d,box,max(14,int(22*unit)),fill=panel,outline=border,width=max(1,round(2*unit)))
        stripe=max(4,round(5*unit))
        _rounded(d,(x0+14,y0+14,x0+14+stripe,y1-14),stripe,fill=_mix(bg,accent,fade))
        tag_col=_mix(bg,accent,fade)
        number=("CAUSE" if i==0 else "EFFET") if kind=="cause_effect" else chr(65+i) if kind=="comparison" else f"{i+1:02d}"
        label(number,x0+round(34*unit),y0+round(21*unit),max(16,round(29*unit)),tag_col,True)
        mid=(x0+round(30*unit),y0+round(64*unit),x1-round(24*unit),y1-round(18*unit))
        _fitted(d,str(item["text"]),mid,strong=True,tint=_mix(bg,(250,251,253),fade))
        if kind in {"steps","cause_effect"} and i<count-1 and fade>.4:
            # Subtle directional relationship, without invented numeric metrics.
            if height>width:
                px=(x0+x1)//2
                py=y1+max(5,int((boxes[i+1][1]-y1)*.5))
                d.ellipse((px-4,py-4,px+4,py+4),fill=_mix(bg,accent,fade))
            else:
                nx=boxes[i+1][0]
                px=(x1+nx)//2
                py=(y0+y1)//2
                d.polygon([(px+4,py),(px-5,py-5),(px-5,py+5)],fill=_mix(bg,accent,fade))
    # Progress bar never encodes a fabricated statistic; it is just elapsed time.
    progress=max(0.0,min(1.0,time_sec/duration))
    py=height-max(23,round(height*.047))
    d.line((margin,py,width-margin,py),fill=(75,92,110),width=max(3,round(5*unit)))
    d.line((margin,py,margin+(width-2*margin)*progress,py),fill=accent,
           width=max(3,round(5*unit)))
    return im


def render_motion_frames(folder: Path, *, spec:dict[str,Any], scene_title:str,
                         scene_number:int,width:int,height:int,duration:float,caption_safe:bool=False) -> int:
    if not (320<=width<=1920 and 320<=height<=1920 and width*height<=2073600):
        raise ValueError("Dimensions du graphique animé non prises en charge.")
    if not math.isfinite(duration) or not .25<=duration<=12:
        raise ValueError("Durée du graphique animé hors limites.")
    kind=spec.get("type")
    items=spec.get("items")
    if kind not in VISUAL_TYPES or not isinstance(items,list) or len(items) not in (1,2,3,4):
        raise ValueError("Spécification de graphique narratif invalide.")
    if (kind in {"focus","cube_rotation","sphere_rotation"} and len(items)!=1 or kind in {"comparison","cause_effect"} and len(items)!=2
        or kind in {"steps","timeline"} and len(items)<2):
        raise ValueError("Nombre d'étapes incorrect pour ce type de schéma.")
    if any(not isinstance(item,dict) or not isinstance(item.get("text"),str)
           or not 5<=len(item["text"].strip())<=125 for item in items):
        raise ValueError("Chaque élément animé doit être une courte citation du récit.")
    folder.mkdir(parents=True,exist_ok=True)
    count=max(2,math.ceil(duration*FRAME_RATE))
    for i in range(count):
        t=(i/FRAME_RATE)
        active_height=round(height*.74) if caption_safe else height
        picture=_draw_frame(width=width,height=active_height,kind=kind,items=items,
            scene_title=scene_title,scene_number=scene_number,time_sec=t,duration=duration)
        if caption_safe:
            full=Image.new("RGB",(width,height),PALETTE[kind][0]);full.paste(picture,(0,0));picture.close();picture=full
        picture.save(folder/f"frame_{i:04d}.png",format="PNG",compress_level=1)
        picture.close()
    return count


async def render_motion_graphic(destination:Path,*,spec:dict[str,Any],
    scene_title:str,scene_number:int,width:int,height:int,fps:int,duration:float,
    workdir:Path,caption_safe:bool=False)->None:
    """FFmpeg encodes low-rate procedural frames to constant film FPS."""
    if not 1<=fps<=30:raise ValueError("Cadence hors limites.")
    frames_dir=Path(tempfile.mkdtemp(prefix="gt-motion-",dir=workdir))
    try:
        await asyncio.to_thread(render_motion_frames,frames_dir,spec=spec,
            scene_title=scene_title,scene_number=scene_number,
            width=width,height=height,duration=duration,caption_safe=caption_safe)
        await run_ffmpeg([
            "-framerate",str(FRAME_RATE),"-i",str(frames_dir/"frame_%04d.png"),
            "-t",f"{duration:.4f}","-vf",f"fps={fps},format=yuv420p",
            "-an","-r",str(fps),"-c:v","libx264","-preset","ultrafast",
            "-threads","1","-pix_fmt","yuv420p","-movflags","+faststart",
            str(destination),
        ],timeout=600)
    finally:
        shutil.rmtree(frames_dir,ignore_errors=True)

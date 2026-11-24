"""Bounded, private evidence from the actual final encoded movie."""
from __future__ import annotations
import base64
import json
import math
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from app.media.ffmpeg import run_ffmpeg, probe_media

MAX_SHOTS = 240
BATCH_SIZE = 3
ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

def review_plan(film: dict) -> list[dict]:
    """Two samples per actual shot, with the exact corresponding narrative excerpt."""
    shots=[]
    offset=0.0
    for scene in sorted(film.get("scenes",[]),key=lambda s:s.get("order",0)):
        for shot in sorted(scene.get("shots",[]),key=lambda s:s.get("order",0)):
            sid=str(shot.get("id",""))
            begin=offset+float(shot["inSec"])
            end=offset+float(shot["outSec"])
            quote=shot.get("visualText") if shot.get("visualMode")=="programmatic" else (shot.get("visualEvidence") or {}).get("narrationQuote")
            if not ID.fullmatch(sid) or not isinstance(quote,str) or not 5<=len(quote.strip())<=280 or not math.isfinite(begin+end) or end<=begin:
                raise ValueError("Plan de contrôle cinématographique incomplet.")
            shots.append({"shotId":sid,"startSec":round(begin,3),"endSec":round(end,3),
                          "quote":quote,"samplesSec":[round(begin+(end-begin)*x,3) for x in (.35,.8)]})
        offset+=float(scene["durationSec"])
    if not 1<=len(shots)<=MAX_SHOTS or len({s["shotId"] for s in shots})!=len(shots):
        raise ValueError("Contrôle cinématographique limité à 240 plans identifiés.")
    return shots

async def collect_review_batches(output: Path, film: dict, directory: Path) -> list[dict]:
    """Contact sheets use only decoded final frames. No model inference here."""
    plan=review_plan(film)
    probe=await probe_media(str(output))
    video=next((s for s in probe.get("streams",[]) if s.get("codec_type")=="video"),{})
    duration=float(video.get("duration") or 0)
    if not math.isfinite(duration) or duration<=0 or plan[-1]["samplesSec"][-1]>=duration:
        raise ValueError("Timeline finale incompatible avec les images de contrôle.")
    batches=[]
    directory.mkdir(parents=True,exist_ok=True)
    cell_w,cell_h=480,300
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    for start in range(0,len(plan),BATCH_SIZE):
        rows=plan[start:start+BATCH_SIZE]
        sheet=Image.new("RGB",(cell_w*2,(cell_h+30)*len(rows)),(18,22,30))
        draw=ImageDraw.Draw(sheet)
        try:
            for row,shot in enumerate(rows):
                for col,t in enumerate(shot["samplesSec"]):
                    png=directory/"sample.png"
                    await run_ffmpeg(["-ss",str(t),"-i",str(output),"-frames:v","1",
                        "-vf","scale=480:300:force_original_aspect_ratio=decrease",
                        "-threads","1",str(png)],timeout=30)
                    if not png.is_file():
                        # Accurate output seek can recover from a bad seek index.
                        await run_ffmpeg(["-i",str(output),"-ss",str(t),"-frames:v","1",
                            "-vf","scale=480:300:force_original_aspect_ratio=decrease",
                            "-threads","1",str(png)],timeout=90)
                    if not png.is_file():
                        raise ValueError(f"Image finale introuvable à {t:.3f}s (plan {shot['shotId']}).")
                    with Image.open(png) as im:
                        x=col*cell_w+(cell_w-im.width)//2
                        y=row*(cell_h+30)+(cell_h-im.height)//2
                        sheet.paste(im,(x,y))
                    png.unlink()
                    draw.text((col*cell_w+8,row*(cell_h+30)+cell_h+5),
                              f"Plan {row+1} | {t:.2f} s",font=font,fill="white")
            index=start//BATCH_SIZE
            jpeg=directory/f"batch_{index:03d}.jpg"
            sheet.save(jpeg,"JPEG",quality=76,optimize=True)
            payload={"version":1,"index":index,"shots":rows,
                     "jpegBase64":base64.b64encode(jpeg.read_bytes()).decode("ascii")}
            jpeg.unlink()
            path=directory/f"batch_{index:03d}.json"
            path.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
            if path.stat().st_size>450000:
                raise ValueError("Lot visuel trop volumineux.")
            batches.append({"index":index,"count":len(rows),"path":path})
        finally:
            sheet.close()
    return batches

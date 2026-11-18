from __future__ import annotations
import html
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
import cairosvg
from PIL import Image, ImageDraw, ImageFont
import subprocess

class GraphicsError(ValueError):
    pass

def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise GraphicsError("Valeur numérique invalide.") from None
    if not math.isfinite(result) or abs(result) > 1e12:
        raise GraphicsError("Valeur numérique hors limites.")
    return result

def chart_to_png(spec: dict[str, Any], destination: Path) -> None:
    # A chart without a traceable source must never look like verified data.
    source = spec.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("name"), str) or not source["name"].strip() or not isinstance(source.get("url"), str) or not source["url"].startswith("https://"):
        raise GraphicsError("Graphique sans source documentée (source.name et source.url HTTPS).")
    if spec.get("projection") is not None and not isinstance(spec["projection"], bool):
        raise GraphicsError("projection doit être un booléen.")
    kind = str(spec.get("type", "bar")).lower()
    if kind not in {"bar", "line", "pie"}:
        raise GraphicsError("Type de graphique non pris en charge.")
    labels = [str(v)[:80] for v in (spec.get("labels") or [])[:20]]
    series = spec.get("series") or []
    if not labels or not isinstance(series, list) or not series:
        raise GraphicsError("Labels ou séries absents.")
    colors = spec.get("colors") or ["#4776e6", "#16a085", "#e67e22", "#9b59b6"]
    if not isinstance(colors, list) or not colors or any(not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors):
        raise GraphicsError("Palette de couleurs invalide.")
    colors = colors[:10]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">',
        '<rect width="1280" height="720" fill="white"/>',
        '<text x="640" y="68" text-anchor="middle" font-family="DejaVu Sans" font-size="32" fill="#172033">' + html.escape(str(spec.get("title", "Graphique"))[:120]) + '</text>']
    parts.append('<text x="100" y="690" font-family="DejaVu Sans" font-size="17" fill="#344054">' +
                 html.escape(("Projection · " if spec.get("projection") else "Source · ") + source["name"][:100]) + '</text>')
    if kind in {"bar", "line"}:
        data = []
        for item in series[:10]:
            if not isinstance(item, dict):
                raise GraphicsError("Série invalide.")
            data.append([_number(v) for v in (item.get("values") or [])[:len(labels)]])
        values = [v for row in data for v in row]
        if not values:
            raise GraphicsError("Séries de données vides.")
        low, high = min(0, min(values)), max(0, max(values))
        span = high - low or 1
        left, right, top, bottom = 100, 1180, 130, 600
        parts.append(f'<path d="M{left} {top} V{bottom} H{right}" stroke="#344054" stroke-width="3" fill="none"/>')
        if kind == "bar":
            slot = (right-left)/len(labels)
            bw = slot/(len(data)+1)
            for si, row in enumerate(data):
                for i, value in enumerate(row):
                    x = left + i*slot + (si+0.1)*bw
                    zero = bottom - (0-low)/span*(bottom-top)
                    y = bottom - (value-low)/span*(bottom-top)
                    parts.append(f'<rect x="{x:.1f}" y="{min(y,zero):.1f}" width="{bw*.8:.1f}" height="{max(1,abs(zero-y)):.1f}" fill="{colors[si%len(colors)]}"/>')
        else:
            for si, row in enumerate(data):
                points = []
                for i, value in enumerate(row):
                    x = left + i*(right-left)/max(1,len(labels)-1)
                    y = bottom - (value-low)/span*(bottom-top)
                    points.append(f"{x:.1f},{y:.1f}")
                parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[si%len(colors)]}" stroke-width="6"/>')
        for i, label in enumerate(labels):
            x = left + (i+0.5)*(right-left)/len(labels)
            parts.append(f'<text x="{x:.1f}" y="645" text-anchor="middle" font-family="DejaVu Sans" font-size="17">{html.escape(label)}</text>')
    else:
        if not isinstance(series[0], dict):
            raise GraphicsError("Série circulaire invalide.")
        values = [_number(v) for v in (series[0].get("values") or [])[:len(labels)]]
        if not values or any(v < 0 for v in values) or sum(values) <= 0:
            raise GraphicsError("Valeurs circulaires invalides.")
        angle, cx, cy, radius = -90.0, 640, 365, 220
        for i, value in enumerate(values):
            sweep = value/sum(values)*360
            end = angle+sweep
            x1, y1 = cx+radius*math.cos(math.radians(angle)), cy+radius*math.sin(math.radians(angle))
            x2, y2 = cx+radius*math.cos(math.radians(end)), cy+radius*math.sin(math.radians(end))
            large = 1 if sweep > 180 else 0
            parts.append(f'<path d="M{cx} {cy} L{x1:.2f} {y1:.2f} A{radius} {radius} 0 {large} 1 {x2:.2f} {y2:.2f} Z" fill="{colors[i%len(colors)]}"/>')
            angle = end
        for i, label in enumerate(labels[:len(values)]):
            parts.append(f'<text x="{100+i*270}" y="660" font-family="DejaVu Sans" font-size="18" fill="{colors[i%len(colors)]}">{html.escape(label)}</text>')
    parts.append("</svg>")
    cairosvg.svg2png(bytestring="".join(parts).encode("utf-8"), write_to=str(destination))

def chart_to_video(spec: dict[str, Any], destination: Path, duration: float, fps: int = 24) -> None:
    """Render a sourced bar/line chart progressively; no arbitrary generated code is executed."""
    if not math.isfinite(duration) or duration <= 0 or duration > 600:
        raise GraphicsError("Durée d’animation invalide.")
    kind = str(spec.get("type", "line")).lower()
    if kind not in {"bar", "line"}:
        raise GraphicsError("L’animation est disponible pour les graphiques à barres et en courbes.")
    labels, series = spec.get("labels") or [], spec.get("series") or []
    if not labels or not series or len(labels) > 20 or len(series) > 10:
        raise GraphicsError("Données de graphique invalides.")
    rows = [[_number(v) for v in (s.get("values") or [])[:len(labels)]] for s in series]
    if not any(rows): raise GraphicsError("Données de graphique vides.")
    palette = spec.get("colors") or ["#7c3aed", "#e85d75", "#e6ad35"]
    if any(not isinstance(c,str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",c) for c in palette):
        raise GraphicsError("Palette invalide.")
    lo, hi = min(0,min(v for row in rows for v in row)), max(0,max(v for row in rows for v in row))
    span = hi-lo or 1; w,h=1280,720; left,right,top,bottom=110,1190,140,590
    frames=max(2,round(duration*max(1,min(30,int(fps)))))
    destination.parent.mkdir(parents=True,exist_ok=True)
    proc=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{w}x{h}","-r",str(max(1,min(30,int(fps)))),"-i","-","-an","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-movflags","+faststart",str(destination)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for fi in range(frames):
            progress=min(1,(fi+1)/max(1,frames*0.82))
            im=Image.new("RGB",(w,h),"#111421"); d=ImageDraw.Draw(im)
            d.text((left,38),str(spec.get("title","Graphique"))[:100],fill="#f4f2fa")
            d.text((left,675),("Projection · " if spec.get("projection") else "Source · ")+str(spec["source"]["name"])[:90],fill="#b9b4c9")
            d.line((left,top,left,bottom,right,bottom),fill="#777386",width=2)
            if kind=="line":
                for si,row in enumerate(rows):
                    n=max(1,min(len(row),math.ceil(progress*len(row))))
                    pts=[]
                    for i,value in enumerate(row[:n]):
                        x=left+i*(right-left)/max(1,len(labels)-1); y=bottom-(value-lo)/span*(bottom-top)
                        pts.append((int(x),int(y)))
                    if len(pts)>1: d.line(pts,fill=palette[si%len(palette)],width=6)
                    for x,y in pts: d.ellipse((x-6,y-6,x+6,y+6),fill=palette[si%len(palette)])
            else:
                slot=(right-left)/len(labels); bw=slot/(len(rows)+1)
                count=math.ceil(progress*len(labels))
                zero=bottom-(0-lo)/span*(bottom-top)
                for si,row in enumerate(rows):
                    for i,value in enumerate(row[:count]):
                        x=left+i*slot+(si+.1)*bw; y=bottom-(value-lo)/span*(bottom-top)
                        y=zero+(y-zero)*min(1,max(0,(progress*len(labels)-i)))
                        d.rectangle((int(x),int(min(y,zero)),int(x+bw*.8),int(max(y,zero))),fill=palette[si%len(palette)])
            for i,label in enumerate(labels):
                x=left+(i+.5)*(right-left)/len(labels); d.text((int(x-30),610),str(label)[:16],fill="#ddd9e7")
            proc.stdin.write(im.tobytes())
        proc.stdin.close(); err=proc.stderr.read(); code=proc.wait()
        if code: raise GraphicsError("Échec de l’encodage du graphique animé : "+err.decode("utf-8","replace")[-200:])
    except Exception:
        if proc.poll() is None: proc.kill()
        proc.wait(); destination.unlink(missing_ok=True); raise

def sanitize_svg_to_png(source: Path, destination: Path) -> None:
    raw = source.read_bytes()
    if len(raw) > 10*1024*1024:
        raise GraphicsError("SVG trop volumineux.")
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise GraphicsError("Déclaration XML interdite.")
    if b"URL(" in upper or b"@IMPORT" in upper:
        raise GraphicsError("Référence CSS externe interdite.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise GraphicsError("Document SVG invalide.") from None
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag in {"script", "foreignobject", "iframe", "object", "embed"}:
            raise GraphicsError("Contenu actif interdit.")
        for key, value in node.attrib.items():
            name = key.split("}")[-1].lower()
            if name.startswith("on"):
                raise GraphicsError("Événement SVG interdit.")
            if name in {"href", "src"} and value and not value.startswith("#"):
                raise GraphicsError("Référence SVG externe interdite.")
            if "url(" in value.lower():
                raise GraphicsError("Référence SVG externe interdite.")
    cairosvg.svg2png(bytestring=raw, write_to=str(destination), output_width=1920, output_height=1080)


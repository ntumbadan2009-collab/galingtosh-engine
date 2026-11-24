"""Data-faithful programmatic story cards.

All lettering comes from the approved narration and scene title. Unlike
unverified stock footage, this visual never claims an unseen fact, person,
object or location. It is drawn with Pillow; no image/video generation model.
"""
from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PALETTES = {
    "focus": ((12, 20, 39), (86, 225, 190)),
    "question": ((22, 21, 48), (245, 189, 87)),
    "contrast": ((24, 19, 36), (244, 119, 152)),
    "process": ((10, 32, 43), (102, 198, 249)),
}


def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size=size)


def _fit_lines(draw, text: str, font, width: int) -> list[str]:
    """Wrap without truncating the narration quote."""
    result: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            proposal = word if not line else line + " " + word
            if line and draw.textbbox((0, 0), proposal, font=font)[2] > width:
                result.append(line)
                line = word
            else:
                line = proposal
        if line:
            result.append(line)
    return result or [""]


def render_code_card(
    destination: Path,
    *, narration_quote: str,
    scene_title: str,
    scene_number: int,
    width: int,
    height: int,
    style: str = "focus",
) -> None:
    """Draw a coherent text/diagram visual, never an invented factual chart."""
    if not isinstance(narration_quote, str) or not 5 <= len(narration_quote.strip()) <= 280:
        raise ValueError("Illustration par code : extrait de narration invalide.")
    if not 320 <= width <= 1920 or not 320 <= height <= 1920 or width * height > 2073600:
        raise ValueError("Dimensions d'illustration non prises en charge.")
    background, accent = PALETTES.get(style, PALETTES["focus"])
    img = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(img)
    sx = width / 1280
    sy = height / 720
    unit = min(sx, sy)
    def p(x: float, y: float) -> tuple[int, int]:
        return round(x*sx), round(y*sy)
    def rect(x0, y0, x1, y1, *, fill, radius=0, outline=None, line=1):
        draw.rounded_rectangle((*p(x0,y0), *p(x1,y1)), round(radius*unit),
                               fill=fill, outline=outline, width=max(1,round(line*unit)))
    # Bounded, subtle grid and a visual hierarchy inspired by documentary explainers.
    for i in range(18):
        x = int((80 + i*70) * sx)
        draw.line((x, 0, x, height), fill=tuple(min(255, c+6) for c in background), width=1)
    for i in range(11):
        y = int((30 + i*70)*sy)
        draw.line((0, y, width, y), fill=tuple(min(255, c+6) for c in background), width=1)
    rect(70, 56, 1210, 664, fill=background, radius=32, outline=tuple(min(255,c+28) for c in background), line=2)
    rect(96, 90, 106, 160, fill=accent, radius=5)
    small = _font(FONT_BOLD, max(12, round(20*unit)))
    draw.text(p(126, 93), f"SÉQUENCE {max(1,int(scene_number)):02d}", font=small, fill=accent)
    label = (str(scene_title or "").strip() or "Illustration narrative")[:90]
    regular = _font(FONT_REGULAR, max(12, round(23*unit)))
    while label and draw.textbbox((0,0),label,font=regular)[2] > round(1010*sx):
        label=label[:-1]
    draw.text(p(126, 133), label, font=regular, fill=(181, 190, 206))
    quote = narration_quote.strip()
    wrap_width = round(1010*sx)
    # Adapt font size, never replace the text with a misleading simplification.
    for font_size in range(max(16, round(60*unit)), max(13, round(29*unit))-1, -2):
        font = _font(FONT_BOLD, font_size)
        lines = _fit_lines(draw, quote, font, wrap_width)
        line_h = int(font_size*1.42)
        if len(lines)*line_h <= round(325*sy) and len(lines) <= 8 and all(draw.textbbox((0,0),line,font=font)[2]<=wrap_width for line in lines):
            break
    else:
        img.close()
        raise ValueError("Citation trop longue pour rester lisible : scinder le plan.")
    y = int(252*sy) - min(0, (len(lines)-3)*int(line_h*0.13))
    for line in lines:
        draw.text((round(126*sx), y), line, font=font, fill=(245, 247, 252))
        y += line_h
    # Nonderivative graphical cues: an editorial progress line and abstract nodes.
    bar_y = int(607*sy)
    draw.line((round(126*sx),bar_y,round(1140*sx),bar_y), fill=(82, 96, 121), width=max(2,round(3*unit)))
    draw.line((round(126*sx),bar_y,round(410*sx),bar_y), fill=accent, width=max(3,round(6*unit)))
    for idx in range(3):
        x = round((1010+idx*48)*sx)
        draw.ellipse((x-round(7*unit),bar_y-round(7*unit),x+round(7*unit),bar_y+round(7*unit)),
                     fill=accent if idx==0 else (92,106,126))
    destination.parent.mkdir(parents=True, exist_ok=True)
    img.save(destination, format="PNG", optimize=True)

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.media.ffmpeg import run_ffmpeg

_ALLOWED = {"fade_in", "fade_out", "grayscale", "vignette", "text_overlay"}


def _escape_drawtext(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%").replace(",", "\\,")


def build_video_filters(effects: list[dict[str, Any]], duration: float, width: int, height: int) -> tuple[list[str], list[str]]:
    filters: list[str] = []
    warnings: list[str] = []
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        kind = str(effect.get("type", ""))
        params = effect.get("params") or {}
        if kind not in _ALLOWED:
            warnings.append(f"Effet « {kind} » non pris en charge : ignoré.")
            continue
        if kind == "grayscale":
            filters.append("hue=s=0")
        elif kind == "vignette":
            filters.append("vignette=PI/5")
        elif kind == "fade_in":
            seconds = max(0.05, min(5.0, float(params.get("durationSec", 1))))
            filters.append(f"fade=t=in:st=0:d={seconds:.3f}")
        elif kind == "fade_out":
            seconds = max(0.05, min(5.0, float(params.get("durationSec", 1))))
            filters.append(f"fade=t=out:st={max(0.0, duration-seconds):.3f}:d={seconds:.3f}")
        elif kind == "text_overlay":
            text = _escape_drawtext(str(params.get("text", ""))[:300])
            if text:
                size = max(12, min(96, int(params.get("fontSize", max(24, width // 28)))))
                position = str(params.get("position", "bottom")).lower()
                y = "h-th-2*text_h" if position == "top" else "(h-text_h)/2" if position == "center" else "h-th-2*text_h"
                filters.append(f"drawtext=text='{text}':fontcolor=white:fontsize={size}:borderw=2:bordercolor=black:x=(w-text_w)/2:y={y}")
    return filters, warnings


async def finish_video(source: Path, destination: Path, filters: list[str], subtitle_file: Path | None = None) -> None:
    if subtitle_file and subtitle_file.is_file():
        path = str(subtitle_file.resolve()).replace("\\", "/").replace(":", "\\:")
        filters.append(f"subtitles='{path}':force_style='FontName=DejaVu Sans,FontSize=24,Outline=2,Shadow=1,MarginV=36'")
    if not filters:
        source.replace(destination)
        return
    await run_ffmpeg([
        "-i", str(source), "-vf", ",".join(filters), "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-threads", "1", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(destination)
    ])

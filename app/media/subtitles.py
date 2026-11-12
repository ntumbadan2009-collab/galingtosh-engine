from __future__ import annotations

from pathlib import Path
from typing import Any


def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def write_srt(subtitles: list[dict[str, Any]], destination: Path, language: str | None = None) -> bool:
    selected = next((s for s in subtitles if language and s.get("language") == language), None)
    selected = selected or (subtitles[0] if subtitles else None)
    if not selected:
        return False
    cues = selected.get("cues") or []
    lines: list[str] = []
    valid = 0
    for cue in cues:
        try:
            start, end = float(cue.get("startSec", 0)), float(cue.get("endSec", 0))
            content = str(cue.get("text", "")).strip()
        except (TypeError, ValueError):
            continue
        if not content or start < 0 or end <= start:
            continue
        valid += 1
        lines.extend([str(valid), f"{_timestamp(start)} --> {_timestamp(end)}", content, ""])
    if not valid:
        return False
    destination.write_text("\n".join(lines), encoding="utf-8-sig")
    return True

from __future__ import annotations

from pathlib import Path
from typing import Any
import textwrap


def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def _caption_chunks(text: str, max_chars: int = 76) -> list[str]:
    """Split long scene captions into short, readable two-line cards."""
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        addition = len(word) + (1 if current else 0)
        if current and length + addition > max_chars:
            chunks.append(" ".join(current))
            current, length = [], 0
        current.append(word)
        length += len(word) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append(" ".join(current))
    return chunks


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
        parts = _caption_chunks(content)
        weights = [max(1, len(part)) for part in parts]
        total_weight = sum(weights)
        cursor = start
        for index, (part, weight) in enumerate(zip(parts, weights)):
            part_end = end if index == len(parts) - 1 else cursor + (end - start) * weight / total_weight
            wrapped = "\n".join(textwrap.wrap(part, width=38, break_long_words=False, break_on_hyphens=False)[:2])
            valid += 1
            lines.extend([str(valid), f"{_timestamp(cursor)} --> {_timestamp(part_end)}", wrapped, ""])
            cursor = part_end
    if not valid:
        return False
    destination.write_text("\n".join(lines), encoding="utf-8-sig")
    return True

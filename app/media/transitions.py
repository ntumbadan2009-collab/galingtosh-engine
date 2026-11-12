from __future__ import annotations
from pathlib import Path
from typing import Any
from app.media.ffmpeg import run_ffmpeg

TRANSITION_MAP = {
    "dissolve": "dissolve", "fade": "fade",
    "slide": "slideleft", "wipe": "wipeleft", "zoom": "zoomin",
}

async def assemble_segments(
    segments: list[Path], shot_ids: list[str | None], durations: list[float],
    transitions: list[dict[str, Any]], output: Path, fps: int, timeout: int,
) -> list[str]:
    if not segments or not (len(segments) == len(shot_ids) == len(durations)):
        raise ValueError("Segments de montage incohérents.")
    by_shot = {str(t["atShotId"]): t for t in transitions
               if isinstance(t, dict) and t.get("atShotId") is not None}
    args: list[str] = []
    graph: list[str] = []
    warnings: list[str] = []
    for i, path in enumerate(segments):
        args += ["-i", str(path)]
        graph.append(f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS,fps={fps},format=yuv420p[v{i}]")
    previous = "v0"
    elapsed = max(0.0, float(durations[0]))
    for i in range(1, len(segments)):
        spec = by_shot.get(shot_ids[i] or "")
        kind = str((spec or {}).get("type", "cut")).lower()
        requested = float((spec or {}).get("durationSec", 0) or 0)
        label = f"joined{i}"
        if not spec or kind == "cut" or requested <= 0:
            graph.append(f"[{previous}][v{i}]concat=n=2:v=1:a=0[{label}]")
            elapsed += max(0.0, float(durations[i]))
        elif kind not in TRANSITION_MAP:
            warnings.append(f"Transition « {kind} » inconnue : coupe franche appliquée.")
            graph.append(f"[{previous}][v{i}]concat=n=2:v=1:a=0[{label}]")
            elapsed += max(0.0, float(durations[i]))
        else:
            d = min(requested, 2.0, max(0.0, float(durations[i])-0.05), max(0.0, elapsed-0.05))
            if d < 0.05:
                warnings.append(f"Transition {kind} trop courte : coupe franche appliquée.")
                graph.append(f"[{previous}][v{i}]concat=n=2:v=1:a=0[{label}]")
                elapsed += max(0.0, float(durations[i]))
            else:
                graph.append(f"[{previous}][v{i}]xfade=transition={TRANSITION_MAP[kind]}:duration={d:.4f}:offset={elapsed-d:.4f}[{label}]")
                elapsed += max(0.0, float(durations[i]))-d
        previous = label
    graph.append(f"[{previous}]null[vout]")
    await run_ffmpeg([*args, "-filter_complex", ";".join(graph), "-map", "[vout]", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-threads", "1",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", str(output)],
        timeout=timeout)
    return warnings

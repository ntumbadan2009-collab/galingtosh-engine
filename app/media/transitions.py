from __future__ import annotations
from pathlib import Path
from typing import Any
from app.media.ffmpeg import run_ffmpeg

TRANSITION_MAP = {"dissolve":"dissolve","fade":"fade","slide":"slideleft","wipe":"wipeleft","zoom":"zoomin"}

async def assemble_segments(segments:list[Path], shot_ids:list[str|None], durations:list[float],
    transitions:list[dict[str,Any]], output:Path, fps:int, timeout:int)->list[str]:
    """Assemble les clips deux par deux : jamais plus de deux flux vidéo décodés en même temps."""
    if not segments or not (len(segments)==len(shot_ids)==len(durations)):
        raise ValueError("Segments de montage incohérents.")
    by_shot={str(t["atShotId"]):t for t in transitions if isinstance(t,dict) and t.get("atShotId") is not None}
    warnings=[]
    current=segments[0]
    elapsed=max(0.0,float(durations[0]))
    for i,next_segment in enumerate(segments[1:],start=1):
        spec=by_shot.get(shot_ids[i] or "")
        kind=str((spec or {}).get("type","cut")).lower()
        try: requested=float((spec or {}).get("durationSec",0) or 0)
        except (TypeError,ValueError): requested=0.0
        merged=output.parent/f"merge_{i:04d}.mp4"
        use_transition=bool(spec and kind!="cut" and requested>0 and kind in TRANSITION_MAP)
        d=min(requested,1.0,max(0.0,float(durations[i])-0.05),max(0.0,elapsed-0.05)) if use_transition else 0.0
        if spec and kind not in TRANSITION_MAP and kind!="cut":
            warnings.append(f"Transition « {kind} » inconnue : coupe franche appliquée.")
        if use_transition and d>=0.05:
            await run_ffmpeg(["-i",str(current),"-i",str(next_segment),"-filter_complex",
                f"[0:v]settb=AVTB,setpts=PTS-STARTPTS,fps={fps},format=yuv420p[a];"
                f"[1:v]settb=AVTB,setpts=PTS-STARTPTS,fps={fps},format=yuv420p[b];"
                f"[a][b]xfade=transition={TRANSITION_MAP[kind]}:duration={d:.4f}:offset={elapsed-d:.4f}[v]",
                "-map","[v]","-an","-c:v","libx264","-preset","ultrafast","-threads","1",
                "-pix_fmt","yuv420p","-r",str(fps),str(merged)],timeout=timeout)
            elapsed+=max(0.0,float(durations[i]))-d
        else:
            listing=output.parent/f"concat_{i:04d}.txt"
            listing.write_text("".join(f"file '{p.resolve()}'\\n" for p in (current,next_segment)),encoding="utf-8")
            await run_ffmpeg(["-f","concat","-safe","0","-i",str(listing),"-c","copy","-an",str(merged)],timeout=timeout)
            listing.unlink(missing_ok=True)
            elapsed+=max(0.0,float(durations[i]))
        if current not in segments: current.unlink(missing_ok=True)
        current=merged
        next_segment.unlink(missing_ok=True)
    if current != output:
        current.replace(output)
    return warnings

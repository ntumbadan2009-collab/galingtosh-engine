from __future__ import annotations
from pathlib import Path
from typing import Any
import math
from app.media.ffmpeg import run_ffmpeg

def _db(value: Any) -> float:
    try:
        value = float(value)
        return max(-60.0, min(12.0, value)) if math.isfinite(value) else 0.0
    except (TypeError, ValueError): return 0.0

async def mix_audio(video: Path, tracks: list[dict], media_files: dict[str, Path], destination: Path,
                    total_duration: float, bitrate_kbps: int = 128, *, editorial: bool = False) -> tuple[bool, list[str]]:
    """Mixage multipiste avec placement temporel, répétition musicale et limiteur."""
    inputs=[]; warnings=[]
    for track in tracks:
        if not isinstance(track,dict) or track.get("disabled"): continue
        source=media_files.get(str(track.get("mediaRef"))) if track.get("mediaRef") else None
        if not source or not source.is_file():
            if track.get("tts"):
                warnings.append(f"Voix TTS indisponible pour la piste {track.get('id','')} : piste ignorée.")
            elif track.get("kind") in {"voiceover","dialogue","music","sfx"}:
                warnings.append(f"Piste audio {track.get('id','')} sans fichier exploitable : ignorée.")
            continue
        volume=_db(track.get("volumeDb",0)); events=track.get("events") or []
        kind=track.get("kind", "sfx")
        # Preserve the foreground voice; this is a static mix policy, not adaptive ducking.
        if editorial and any(t.get("kind") in {"voiceover", "dialogue"} and not t.get("disabled") for t in tracks if isinstance(t, dict)):
            if kind == "music": volume = min(volume, -16.0)
            elif kind == "sfx": volume = min(volume, -10.0)
        if not events: inputs.append((source,0.0,total_duration,kind=="music",volume,kind))
        else:
            for event in events:
                if not isinstance(event,dict): continue
                try:
                    start=max(0.0,float(event.get("startSec",0)))
                    duration=float(event.get("durationSec",total_duration-start))
                except (TypeError,ValueError): continue
                duration=min(duration,total_duration-start)
                if start<total_duration and duration>0: inputs.append((source,start,duration,False,volume,kind))
    if not inputs: return False,list(dict.fromkeys(warnings))
    args=["-i",str(video)]
    for source,_,_,loop,_,_ in inputs:
        if loop: args += ["-stream_loop","-1"]
        args += ["-i",str(source)]
    graph=[]; labels=[]
    for index,(_,start,duration,_,volume,kind) in enumerate(inputs,start=1):
        label=f"a{index}"; delay=round(start*1000)
        fade=min(0.35,duration/4) if kind=="music" else min(0.03,duration/4)
        graph.append(f"[{index}:a]atrim=duration={duration:.4f},asetpts=PTS-STARTPTS,"
                     f"aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"volume={volume:.2f}dB,afade=t=in:d={fade:.4f},"
                     f"afade=t=out:st={max(0,duration-fade):.4f}:d={fade:.4f},"
                     f"adelay={delay}:all=1,apad,atrim=duration={total_duration:.4f}[{label}]")
        # Mix every prepared input in one graph. The previous nested group
        # graph could leave FFmpeg with unbound labels on films combining
        # multiple scene narrations and a procedural music bed.
        labels.append(f"[{label}]")
    fade_duration = min(0.08 if editorial else 1.0, max(0.05, total_duration))
    fade_start = max(0.0, total_duration - fade_duration)
    if len(labels) == 1:
        graph.append(f"{labels[0]}anull[mixed]")
    else:
        graph.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0:dropout_transition=2[mixed]")
    graph.append(f"[mixed]alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=11,"
                 f"afade=t=out:st={fade_start:.4f}:d={fade_duration:.4f}[aout]")
    await run_ffmpeg([*args,"-filter_complex",";".join(graph),"-map","0:v:0","-map","[aout]","-c:v","copy",
        "-c:a","aac","-b:a",f"{max(64,min(256,int(bitrate_kbps)))}k","-t",f"{total_duration:.4f}",
        "-movflags","+faststart",str(destination)],timeout=max(600,int(total_duration*3)))
    return True,list(dict.fromkeys(warnings))

from __future__ import annotations
from pathlib import Path
from typing import Any
from app.media.ffmpeg import run_ffmpeg

def _db(value: Any) -> float:
    try: return max(-60.0, min(12.0, float(value)))
    except (TypeError, ValueError): return 0.0

async def mix_audio(video: Path, tracks: list[dict], media_files: dict[str, Path], destination: Path,
                    total_duration: float, bitrate_kbps: int = 128) -> tuple[bool, list[str]]:
    """Mixage multipiste avec placement temporel, répétition musicale et limiteur."""
    inputs=[]; warnings=[]
    for track in tracks:
        if not isinstance(track,dict): continue
        if track.get("tts"): warnings.append("Voix TTS non disponible : fournissez un fichier audio pour cette piste.")
        source=media_files.get(str(track.get("mediaRef"))) if track.get("mediaRef") else None
        if not source or not source.is_file():
            if track.get("kind") in {"voiceover","dialogue","music","sfx"}:
                warnings.append(f"Piste audio {track.get('id','')} sans fichier exploitable : ignorée.")
            continue
        volume=_db(track.get("volumeDb",0)); events=track.get("events") or []
        if not events: inputs.append((source,0.0,total_duration,track.get("kind")=="music",volume))
        else:
            for event in events:
                if not isinstance(event,dict): continue
                try:
                    start=max(0.0,float(event.get("startSec",0)))
                    duration=float(event.get("durationSec",total_duration-start))
                except (TypeError,ValueError): continue
                duration=min(duration,total_duration-start)
                if start<total_duration and duration>0: inputs.append((source,start,duration,False,volume))
    if not inputs: return False,list(dict.fromkeys(warnings))
    args=["-i",str(video)]
    for source,_,_,loop,_ in inputs:
        if loop: args += ["-stream_loop","-1"]
        args += ["-i",str(source)]
    graph=[]; labels=[]
    for index,(_,start,duration,_,volume) in enumerate(inputs,start=1):
        label=f"a{index}"; delay=round(start*1000)
        graph.append(f"[{index}:a]atrim=duration={duration:.4f},asetpts=PTS-STARTPTS,volume={volume:.2f}dB,adelay={delay}:all=1,apad,atrim=duration={total_duration:.4f}[{label}]")
        labels.append(f"[{label}]")
    graph.append("".join(labels)+f"amix=inputs={len(labels)}:duration=longest:dropout_transition=2,alimiter=limit=0.95[aout]")
    await run_ffmpeg([*args,"-filter_complex",";".join(graph),"-map","0:v:0","-map","[aout]","-c:v","copy",
        "-c:a","aac","-b:a",f"{max(64,min(256,int(bitrate_kbps)))}k","-t",f"{total_duration:.4f}",
        "-movflags","+faststart",str(destination)],timeout=max(600,int(total_duration*3)))
    return True,list(dict.fromkeys(warnings))

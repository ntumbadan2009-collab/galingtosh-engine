from __future__ import annotations
import math
from pathlib import Path
from typing import Any
from app.media.ffmpeg import run_ffmpeg,probe_media,FFmpegError

TRANSITION_MAP={"dissolve":"dissolve","fade":"fade","slide":"slideleft","wipe":"wipeleft","zoom":"zoomin"}

async def assemble_segments(segments:list[Path],shot_ids:list[str|None],durations:list[float],
    transitions:list[dict[str,Any]],output:Path,fps:int,timeout:int)->list[str]:
    """Frame-accurate, linear assembly. Only the incoming shot is encoded for
    a transition, using the actual last frame of the preceding shot.
    All clips share a codec, CFR clock, timebase and zero B frames before concat.
    Avoid mixing reordered DTS/PTS from incompatible encoders, which shortened
    a 150-second test to 125 seconds of video while audio still ran to 150.
    """
    if not segments or not(len(segments)==len(shot_ids)==len(durations)) or not 1<=fps<=30:
        raise ValueError("Segments de montage incohérents.")
    by_shot={str(t["atShotId"]):t for t in transitions if isinstance(t,dict) and t.get("atShotId") is not None}
    warnings=[]; parts=[]; previous_frames=0; elapsed=0.0; total_frames=0
    opts=["-an","-c:v","libx264","-preset","veryfast","-crf","21","-bf","0","-threads","1",
          "-pix_fmt","yuv420p","-r",str(fps),"-video_track_timescale",str(fps*1000)]
    listing=output.parent/"assembly_concat.txt"
    last=output.parent/"assembly_last.png"
    try:
        for i,(source,shot,duration) in enumerate(zip(segments,shot_ids,durations)):
            duration=float(duration)
            if not math.isfinite(duration) or duration<=0:raise FFmpegError("Durée de plan invalide.")
            elapsed+=duration
            boundary=round(elapsed*fps)
            frames=boundary-total_frames
            if frames<1:raise FFmpegError("Plan inférieur à une image vidéo.")
            raw=await probe_media(str(source))
            stream=next((s for s in raw.get("streams",[]) if s.get("codec_type")=="video"),{})
            actual=float(stream.get("duration") or raw.get("format",{}).get("duration") or 0)
            if not math.isfinite(actual) or abs(actual-duration)>max(.12,2/fps):
                raise FFmpegError(f"Plan {shot or i+1}: durée vidéo réelle {actual:.3f}s, cible {duration:.3f}s.")
            spec=by_shot.get(shot or "") if i else None
            kind=str((spec or {}).get("type","cut")).lower()
            try:requested=float((spec or {}).get("durationSec",0))
            except (TypeError,ValueError):requested=0.0
            dframes=min(round(max(0,min(2.0,requested))*fps),frames-1) if math.isfinite(requested) and kind in TRANSITION_MAP and i else 0
            if spec and kind not in TRANSITION_MAP and kind!="cut":
                warnings.append(f"Transition « {kind} » inconnue : coupe franche appliquée.")
            part=output.parent/f"assembly_part_{i:04d}.mp4"
            # Padding is limited to two frames for normal rounding; real media
            # shorter than the requested duration is rejected above.
            fit=f"tpad=stop_mode=clone:stop_duration={2/fps:.6f},settb=AVTB,setpts=PTS-STARTPTS,fps={fps},trim=end_frame={frames},format=yuv420p"
            if dframes>0:
                last.unlink(missing_ok=True)
                await run_ffmpeg(["-i",str(parts[-1]),"-vf",f"select='eq(n,{previous_frames-1})'","-frames:v","1","-threads","1",str(last)],timeout=timeout)
                if not last.is_file():raise FFmpegError("Dernière image de transition inaccessible.")
                d=dframes/fps
                graph=(f"[0:v]trim=end_frame={dframes+1},settb=AVTB,setpts=PTS-STARTPTS,fps={fps},format=yuv420p[a];"
                       f"[1:v]{fit}[b];[a][b]xfade=transition={TRANSITION_MAP[kind]}:duration={d:.6f}:offset=0,format=yuv420p[v]")
                args=["-loop","1","-framerate",str(fps),"-i",str(last),"-i",str(source),"-filter_complex",graph,"-map","[v]"]
            else:
                args=["-i",str(source),"-vf",fit,"-map","0:v:0"]
            await run_ffmpeg([*args,"-frames:v",str(frames),*opts,str(part)],timeout=timeout)
            p=await probe_media(str(part))
            v=next((s for s in p.get("streams",[]) if s.get("codec_type")=="video"),{})
            if int(v.get("nb_frames") or 0)!=frames:
                raise FFmpegError(f"Le plan {shot or i+1} ne contient pas le nombre d'images attendu.")
            parts.append(part);previous_frames=frames;total_frames=boundary
            source.unlink(missing_ok=True)
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts),encoding="utf-8")
        await run_ffmpeg(["-f","concat","-safe","0","-i",str(listing),"-map","0:v:0","-c","copy","-an",
                          "-video_track_timescale",str(fps*1000),"-movflags","+faststart",str(output)],timeout=timeout)
        info=await probe_media(str(output))
        stream=next((s for s in info.get("streams",[]) if s.get("codec_type")=="video"),{})
        actual=float(stream.get("duration") or 0)
        if int(stream.get("nb_frames") or 0)!=total_frames or abs(actual-total_frames/fps)>1/fps:
            raise FFmpegError("Assemblage : durée ou nombre d'images incorrect.")
        return warnings
    finally:
        listing.unlink(missing_ok=True);last.unlink(missing_ok=True)
        for part in parts:part.unlink(missing_ok=True)

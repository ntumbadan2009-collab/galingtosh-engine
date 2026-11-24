"""Duration-aware centred digital camera moves and matched sound accents."""
from __future__ import annotations
import math
import wave
from array import array
from pathlib import Path

def zoom_filter(camera: str, width: int, height: int, fps: int, duration: float) -> str:
    frames = max(2, round(duration*fps))
    p = f"min(1,on/{frames-1})"
    ease = f"({p})*({p})*(3-2*({p}))"
    zoom = f"1+0.14*({ease})" if camera == "zoom_in" else f"1.14-0.14*({ease})"
    return (f"zoompan=z='{zoom}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
            f":d=1:s={width}x{height}:fps={fps}")

def accent_events(film: dict) -> list[dict]:
    audio = film.get("audio") or {}
    if audio.get("editorialAccents") is False:
        return []
    manual = [e for t in audio.get("tracks",[]) if t.get("kind")=="sfx" and not t.get("disabled")
              for e in t.get("events",[])]
    transitions = {str(t.get("atShotId")):t for t in film.get("transitions",[]) if t.get("type")=="zoom"}
    events = []
    offset = 0.0
    last = -10.0
    for scene in sorted(film.get("scenes",[]),key=lambda s:s.get("order",0)):
        for shot in sorted(scene.get("shots",[]),key=lambda s:s.get("order",0)):
            start = offset+float(shot["inSec"])
            duration = float(shot["outSec"])-float(shot["inSec"])
            transition = transitions.get(str(shot.get("id"))) if start > .08 else None
            camera = (shot.get("camera") or {}).get("type")
            if duration < 1.5 or start-last<4.0:
                continue
            if not transition and (camera not in {"zoom_in","zoom_out"} or shot.get("visualMode")=="programmatic"):
                continue
            length = min(.65, duration*.35, float(transition.get("durationSec",.35))) if transition else min(.55,duration*.25)
            if length < .12:
                continue
            if any(float(e["startSec"]) < start+length+.2 and
                   float(e["startSec"])+float(e["durationSec"]) > start-.2 for e in manual):
                continue
            events.append({"startSec":round(start,3),"durationSec":round(length,3),"shotId":shot.get("id"),
                           "kind":"zoom_transition" if transition else camera})
            last=start
        offset+=float(scene["durationSec"])
    return events

def render_accents(events: list[dict], duration: float, output: Path) -> None:
    import random
    rate=16000
    samples=array("h",[0])*max(1,round(duration*rate))
    for idx,event in enumerate(events):
        rng=random.Random(4000+idx)
        begin=round(event["startSec"]*rate)
        n=max(1,round(event["durationSec"]*rate))
        previous=0.0
        for i in range(min(n,len(samples)-begin)):
            p=i/n
            noise=rng.uniform(-1,1)
            previous=.82*previous+.18*noise
            envelope=math.sin(math.pi*p)**2
            value=(.65*previous+.22*noise)*envelope
            samples[begin+i]=int(max(-32767,min(32767,samples[begin+i]+value*26000)))
    import sys
    if sys.byteorder!="little":samples.byteswap()
    with wave.open(str(output),"wb") as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate)
        out.writeframes(samples.tobytes())

"""Original deterministic multi-voice score; no downloaded recordings or melody corpus."""
from __future__ import annotations
import math
import wave
from array import array
from pathlib import Path
import sys

RATE=22050
# Common tonal centre; genre-neutral, original algorithmic note patterns.
MOODS={
    "calm":(68,(0,3,7),.18),"hopeful":(96,(0,4,7),.45),
    "tense":(108,(0,1,7),.55),"sad":(62,(0,3,7),.12),
    "wonder":(80,(0,5,7),.3),"neutral":(82,(0,4,7),.23)
}

def hz(note:int)->float:return 440*2**((note-69)/12)

def compose_score(scenes:list[dict],cues:list[dict],output:Path)->bool:
    by_id={str(c["sceneId"]):c for c in cues}
    def enabled(scene):
        cue=by_id.get(str(scene.get("id")),{})
        return cue.get("mood") in MOODS and float(cue.get("intensity",0))>0
    if not any(enabled(s) for s in scenes):return False
    output.parent.mkdir(parents=True,exist_ok=True)
    offset=0.0
    written=0
    with wave.open(str(output),"wb") as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(RATE)
        for scene in scenes:
            duration=float(scene["durationSec"])
            count=round((offset+duration)*RATE)-written
            cue=by_id.get(str(scene.get("id")),{})
            active=enabled(scene)
            bpm,intervals,pulse=MOODS.get(cue.get("mood"),MOODS["neutral"])
            intensity=max(0,min(1,float(cue.get("intensity",0)))) if active else 0
            beat=60/bpm
            notes=[hz(45+i) for i in intervals]
            bass=hz(33)
            pattern=[notes[i%3]*2 for i in (0,2,1,2,0,1,2,1)]
            for start in range(0,count,RATE):
                n=min(RATE,count-start)
                pcm=array("h")
                if not intensity:
                    pcm=array("h",[0])*(n*2)
                else:
                    for j in range(n):
                        t=(start+j)/RATE
                        global_t=offset+t
                        phase=(t/beat)%1
                        index=int(t/beat)%8
                        chord=sum(math.sin(math.tau*f*global_t) for f in notes)/3
                        pad=chord*(.45+.08*math.sin(math.tau*global_t/5))
                        # Plucked voice, soft bass pulses, low percussion. Smooth envelope at beat boundaries.
                        env=min(1,phase*20)*math.exp(-5*phase)
                        pluck=math.sin(math.tau*pattern[index]*phase*beat)*env*.25
                        low=math.sin(math.tau*bass*phase*beat)*env*.24
                        drum=math.sin(math.tau*(58*phase*beat-15*(phase*beat)**2))*min(1,phase*40)*math.exp(-22*phase)*pulse*.19
                        fade=min(1,t/.45,max(0,(duration-t)/.6))
                        gain=intensity*fade*.42
                        left=(pad+pluck*.85+low+drum)*gain
                        right=(pad+pluck*1.15+low+drum)*gain
                        pcm.extend((round(max(-1,min(1,left))*32767),round(max(-1,min(1,right))*32767)))
                if sys.byteorder!="little":pcm.byteswap()
                out.writeframesraw(pcm.tobytes())
            written+=count
            offset+=duration
    return True

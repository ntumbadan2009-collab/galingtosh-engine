"""Procedural note sequencer and sound effects; no external API or samples."""
from __future__ import annotations

import math
import struct
import wave
import random
from pathlib import Path

RATE = 16000
# MIDI note numbers for small triads; the Python synthesizer renders them to WAV.
MIDI_CHORDS = {
    "calm": (45, 48, 52), "hopeful": (45, 49, 52),
    "tense": (45, 46, 52), "sad": (45, 48, 53),
    "wonder": (45, 50, 52), "neutral": (43, 47, 50),
}


def compose_bed(scenes: list[dict], cues: list[dict], output: Path) -> bool:
    """Render a continuous pad, preserving a common tonal centre between scenes.

    Each cue refers to a scene id. An absent cue, silence mood, or zero intensity
    produces intentional silence. No input audio or third-party sound bank is used.
    """
    by_scene = {str(c["sceneId"]): c for c in cues}
    if not any(float(c.get("intensity", 0)) > 0 and c.get("mood") != "silence" for c in cues):
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        offset = 0.0
        for scene in scenes:
            duration = float(scene["durationSec"])
            count = round(duration * RATE)
            cue = by_scene.get(str(scene.get("id")), {})
            mood = cue.get("mood", "silence")
            intensity = float(cue.get("intensity", 0))
            notes = MIDI_CHORDS.get(mood)
            # A soft pad with moving harmonics; bounded level leaves narration room.
            frequencies = [440 * 2 ** ((note - 69) / 12) for note in notes] if notes else []
            for begin in range(0, count, RATE):
                end = min(count, begin + RATE)
                block = bytearray((end - begin) * 2)
                for i in range(begin, end):
                    t = i / RATE
                    fade = min(1, t / 0.8, max(0, (duration - t) / 0.8))
                    movement = 0.78 + 0.22 * math.sin(2 * math.pi * (offset + t) / 7)
                    sample = sum(math.sin(2 * math.pi * f * (offset + t)) * 0.65 +
                                 math.sin(2 * math.pi * f * 2 * (offset + t)) * 0.12
                                 for f in frequencies) / max(1, len(frequencies))
                    value = int(max(-1, min(1, sample * fade * movement * intensity * 0.24)) * 32767)
                    struct.pack_into("<h", block, (i - begin) * 2, value)
                wav.writeframesraw(block)
            offset += duration
    return True


def synthesize_effect(requested: str, output: Path, duration: float = 2.0) -> bool:
    """Synthesize a small deterministic effect only for supported, explicit categories."""
    text = requested.casefold()
    if any(word in text for word in ("pas", "footstep", "marche")): kind = "steps"
    elif any(word in text for word in ("impact", "coup", "claquement", "clap")): kind = "impact"
    elif any(word in text for word in ("pluie", "rain")): kind = "rain"
    elif any(word in text for word in ("vent", "wind")): kind = "wind"
    elif any(word in text for word in ("whoosh", "balayage", "transition")): kind = "whoosh"
    else: return False
    count = max(1, min(RATE * 12, round(duration * RATE)))
    rng = random.Random(f"galingtosh:{kind}:{requested}")
    samples = [0.0] * count
    if kind == "steps":
        for center in range(int(.15*RATE), count, int(.55*RATE)):
            for j in range(min(int(.16*RATE), count-center)):
                t=j/RATE; env=math.exp(-24*t); noise=rng.uniform(-1,1)
                samples[center+j] += (noise*.6 + math.sin(2*math.pi*75*t)*.4)*env
    elif kind == "impact":
        for i in range(count):
            t=i/RATE; samples[i]=(rng.uniform(-1,1)*.75+math.sin(2*math.pi*(100-35*min(t,1))*t)*.25)*math.exp(-5*t)
    else:
        prev=0.0
        for i in range(count):
            t=i/RATE; noise=rng.uniform(-1,1)
            if kind=="rain":
                prev=.88*prev+.12*noise
                value=prev*.55 + (noise*.35 if rng.random()<.08 else 0)
                env=min(1,t*3,max(0,(duration-t)*3))
            elif kind=="wind":
                prev=.97*prev+.03*noise; env=.3+.7*(.5+.5*math.sin(2*math.pi*t/3))
                value=prev*env*.8
            else:
                env=math.sin(math.pi*min(1,t/max(duration,.01)))**2
                value=noise*env*.65
            samples[i]=value
    peak=max((abs(v) for v in samples),default=1) or 1
    output.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(output),"wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE)
        for start in range(0,count,RATE):
            block=samples[start:start+RATE]
            wav.writeframes(b"".join(struct.pack("<h",int(max(-1,min(1,v/peak*.42))*32767)) for v in block))
    return True

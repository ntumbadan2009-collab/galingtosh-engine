"""Measure the actual final audio stream, not perceived emotion or speech clarity."""
from __future__ import annotations
import asyncio
import json
import math
import re
from pathlib import Path
from app.media.ffmpeg import require_binary, FFmpegError

def parse_loudness(log: str) -> dict:
    for block in reversed(re.findall(r"\{[^{}]*\}", log, re.S)):
        try:
            obj=json.loads(block)
            if not {"input_i","input_tp","input_lra"} <= obj.keys(): continue
            vals={}
            for k,name in (("input_i","integrated_lufs"),("input_tp","true_peak_dbtp"),("input_lra","loudness_range_lu")):
                v=float(obj[k])
                vals[name]=round(v,2) if math.isfinite(v) else None
            flags=[]
            if vals["integrated_lufs"] is None: flags.append("integrated_loudness_unmeasurable")
            elif not -22 <= vals["integrated_lufs"] <= -12: flags.append("loudness_outside_review_range")
            if vals["true_peak_dbtp"] is None: flags.append("peak_unmeasurable")
            elif vals["true_peak_dbtp"] > -1: flags.append("high_true_peak")
            return {"version":1,"status":"measured","metrics":vals,"review_flags":flags,"semantic_audio_review":"not_performed"}
        except (ValueError,TypeError): continue
    raise ValueError("Final audio measurement unavailable")

async def inspect_final_audio(path: Path, duration: float) -> dict:
    proc=await asyncio.create_subprocess_exec(require_binary("ffmpeg"),"-hide_banner","-nostats","-loglevel","info",
      "-threads","1","-filter_threads","1","-i",str(path),"-map","0:a:0","-vn",
      "-af","loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json","-f","null","-",
      stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
    try:
        _,err=await asyncio.wait_for(proc.communicate(),timeout=max(60,min(1800,duration*3)))
    except (asyncio.TimeoutError,asyncio.CancelledError):
        if proc.returncode is None: proc.kill()
        await proc.communicate()
        raise
    if proc.returncode: raise FFmpegError("Final audio measurement failed")
    return parse_loudness(err.decode("utf-8","replace"))

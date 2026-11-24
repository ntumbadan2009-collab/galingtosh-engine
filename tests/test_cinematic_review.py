import json
import shutil
import pytest
from app.core.cinematic_review import review_plan,collect_review_batches
from app.media.ffmpeg import run_ffmpeg
from app.media.audio import mix_audio

def film():
    return {"scenes":[{"durationSec":4,"shots":[{"id":"one","inSec":0,"outSec":2,"visualMode":"programmatic","visualText":"Une première étape."},{"id":"two","inSec":2,"outSec":4,"visualMode":"programmatic","visualText":"Une seconde étape."}]}]}

def test_review_plan():
    rows=review_plan(film())
    assert len(rows)==2 and rows[0]["samplesSec"]==[.7,1.6] and rows[1]["samplesSec"]==[2.7,3.6]
    f=film();f["scenes"][0]["shots"][0]["id"]="two"
    with pytest.raises(ValueError):review_plan(f)

@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="FFmpeg absent")
async def test_contact_sheet_and_adaptive_audio(tmp_path):
    v=tmp_path/"real.mp4"
    await run_ffmpeg(["-f","lavfi","-i","testsrc2=s=640x360:r=24","-t","4","-c:v","libx264","-pix_fmt","yuv420p",str(v)])
    batches=await collect_review_batches(v,film(),tmp_path/"review")
    data=json.loads(batches[0]["path"].read_text())
    assert len(batches)==1 and len(data["shots"])==2 and data["jpegBase64"].startswith("/9j/")
    files={}
    for key,freq in [("voice",600),("music",200)]:
        dest=tmp_path/(key+".wav")
        await run_ffmpeg(["-f","lavfi","-i",f"sine=frequency={freq}:duration=4",str(dest)])
        files[key]=dest
    dest=tmp_path/"mixed.mp4"
    ok,_=await mix_audio(v,[{"kind":"voiceover","mediaRef":"voice"},{"kind":"music","mediaRef":"music"}],files,dest,4,editorial=True,adaptive=True)
    assert ok and dest.stat().st_size>0

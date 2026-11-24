import copy
import shutil
import pytest
from app.core.variant_trials import validate_trial,render_trial
from app.media.ffmpeg import run_ffmpeg

def films():
    quote="Le cube tourne autour de son axe."
    a={"info":{"title":"Comparaison","visualPolicy":"strict","editorialLevel":5},"format":{"aspect":"16:9","fps":12},"render":{"resolution":"720p"},
       "media":[],"scenes":[{"id":"s","title":"Géométrie","durationSec":3,"order":1,"narrativeGoal":quote,"shots":[
       {"id":"p","order":1,"inSec":0,"outSec":3,"visualMode":"programmatic","visualText":quote,"cardStyle":"focus"}]}]}
    b=copy.deepcopy(a)
    b["scenes"][0]["shots"][0]["visualSpec"]={"type":"cube_rotation","items":[{"text":quote}]}
    return a,b

def test_invariants():
    a,b=films()
    validate_trial(a,b)
    with pytest.raises(ValueError):validate_trial(a,a)
    b["scenes"][0]["durationSec"]=4
    with pytest.raises(ValueError):validate_trial(a,b)
    a,b=films();b["audio"]={"tracks":[]}
    with pytest.raises(ValueError):validate_trial(a,b)

@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="FFmpeg required")
async def test_actual_alternative_mp4_and_no_fabricated_winner(tmp_path):
    a,b=films()
    original=copy.deepcopy(b)
    result=await render_trial(a,b,{},tmp_path/"trial")
    assert result["winner"] is None and result["status"]=="needs_artistic_review"
    assert result["candidates"][0]["sha256"]!=result["candidates"][1]["sha256"]
    assert all(c["report"]["duration_seconds"]==3 and c["report"]["editorial_quality"]["passed"] for c in result["candidates"])
    assert b==original
    import json
    paired=json.loads((tmp_path/"trial"/result["pairedEvidence"][0]["file"]).read_text())
    assert paired["candidateHashes"]["A"]==result["candidates"][0]["sha256"]
    assert paired["shots"][0]["shotId"]=="p" and paired["jpegBase64"].startswith("/9j/")

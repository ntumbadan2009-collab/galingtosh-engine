import math
import pytest
from app.media.final_audio_review import parse_loudness, inspect_final_audio
from app.media.ffmpeg import run_ffmpeg

def test_audio_metrics_and_unmeasurable_silence():
    r=parse_loudness('noise {"input_i":"-16.2","input_tp":"-1.5","input_lra":"4.0"} tail')
    assert r["metrics"]["integrated_lufs"]==-16.2
    assert not r["review_flags"]
    assert r["semantic_audio_review"]=="not_performed"
    silent=parse_loudness('{"input_i":"-inf","input_tp":"-inf","input_lra":"0"}')
    assert silent["metrics"]["integrated_lufs"] is None
    assert "integrated_loudness_unmeasurable" in silent["review_flags"]
    loud=parse_loudness('{"input_i":"-8","input_tp":"0","input_lra":"1"}')
    assert "high_true_peak" in loud["review_flags"]
    with pytest.raises(ValueError):parse_loudness("no measurement")

@pytest.mark.asyncio
async def test_real_final_audio_decode(tmp_path):
    path=tmp_path/"tone.wav"
    await run_ffmpeg(["-f","lavfi","-i","sine=frequency=440:sample_rate=48000","-t","4",str(path)])
    r=await inspect_final_audio(path,4)
    assert r["status"]=="measured"
    assert math.isfinite(r["metrics"]["integrated_lufs"])
    assert r["semantic_audio_review"]=="not_performed"

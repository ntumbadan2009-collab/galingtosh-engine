import shutil
import pytest
from app.core.editorial_repair import replace_with_grounded_card, repair_unavailable_media
from app.core.editorial import inspect_render
from app.media.ffmpeg import run_ffmpeg, probe_media

def example():
    shot={"id":"s","inSec":0,"outSec":3,"mediaRef":"x","visualEvidence":{"narrationQuote":"La chaleur dilate le métal."}}
    return {"info":{"editorialLevel":3,"visualPolicy":"strict"},"media":[{"id":"x","kind":"video"}],"scenes":[{"narration":{"text":"La chaleur dilate le métal."},"shots":[shot]}]},shot

@pytest.mark.asyncio
async def test_missing_media_replaced_without_timing_change():
    film,shot=example()
    warnings=await repair_unavailable_media(film,{})
    assert warnings and shot["visualMode"]=="programmatic"
    assert shot["outSec"]==3 and shot["visualText"]=="La chaleur dilate le métal."
    assert "mediaRef" not in shot

def test_no_fabricated_fallback():
    film,shot=example()
    shot["visualEvidence"]["narrationQuote"]="Une autre chose."
    assert not replace_with_grounded_card(film["scenes"][0],shot)
    assert shot["mediaRef"]=="x"

@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="FFmpeg absent")
async def test_black_render_rejected(tmp_path):
    p=tmp_path/"black.mp4"
    await run_ffmpeg(["-f","lavfi","-i","color=black:s=320x180:r=24","-t","2","-c:v","libx264","-pix_fmt","yuv420p",str(p)])
    qa=await inspect_render(p,await probe_media(str(p)),2,False,[],24)
    assert not qa["passed"] and qa["black_intervals"]

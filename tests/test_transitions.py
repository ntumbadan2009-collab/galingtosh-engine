import shutil
import subprocess
import pytest
from app.media.transitions import assemble_segments
from app.media.ffmpeg import probe_media

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg/ffprobe requis")

@pytest.mark.asyncio
async def test_dissolve_transition_shortens_timeline(tmp_path):
    clips=[]
    for name,color in [("one","red"),("two","blue")]:
        path=tmp_path/f"{name}.mp4"
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-f","lavfi","-i",
                        f"color=c={color}:s=320x180:r=24","-t","1","-pix_fmt","yuv420p",str(path)],check=True)
        clips.append(path)
    output=tmp_path/"joined.mp4"
    warnings=await assemble_segments(clips,["shot1","shot2"],[1.0,1.0],
        [{"atShotId":"shot2","type":"dissolve","durationSec":0.25}],output,24,30)
    info=await probe_media(str(output))
    duration=float(info["format"]["duration"])
    assert output.is_file()
    assert duration == pytest.approx(1.75,abs=0.15)
    assert warnings == []

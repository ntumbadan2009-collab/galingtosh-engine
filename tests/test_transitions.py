import shutil
import subprocess
import pytest
from app.media.transitions import assemble_segments
from app.media.ffmpeg import probe_media

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg/ffprobe requis")

@pytest.mark.asyncio
async def test_dissolve_transition_preserves_timeline(tmp_path):
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
    assert duration == pytest.approx(2.0,abs=0.15)
    assert warnings == []


@pytest.mark.asyncio
async def test_mixed_b_frames_and_multiple_transitions_keep_all_frames(tmp_path):
    from app.media.ffmpeg import run_ffmpeg
    clips=[]
    for i in range(12):
        path=tmp_path/f"part_{i}.mp4"
        await run_ffmpeg(["-f","lavfi","-i",f"color=c={'red' if i%2 else 'blue'}:s=320x180:r=12","-t","2",
            "-c:v","libx264","-preset","veryfast" if i%2 else "ultrafast","-threads","1","-pix_fmt","yuv420p",str(path)])
        clips.append(path)
    result=tmp_path/"assembled.mp4"
    await assemble_segments(clips,[str(i) for i in range(12)],[2.0]*12,
        [{"atShotId":str(i),"type":"zoom","durationSec":.3} for i in (2,5,8,10)],result,12,30)
    p=await probe_media(str(result));v=next(s for s in p["streams"] if s["codec_type"]=="video")
    assert int(v["nb_frames"])==288 and float(v["duration"])==pytest.approx(24,abs=.05)
    sample=tmp_path/"last.png"
    await run_ffmpeg(["-ss","23.8","-i",str(result),"-frames:v","1",str(sample)])
    assert sample.is_file()

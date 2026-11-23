"""Real FFmpeg frame sampling: rejects out-of-bounds or inaccessible clips."""
import base64
import shutil
import subprocess

import pytest
from app.media.evidence_frames import sample_visual_evidence

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg/ffprobe required",
)


@pytest.mark.asyncio
async def test_extract_three_frames_from_real_video(tmp_path):
    video = tmp_path / "source.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=2.2",
        "-an", "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p",
        "-y", str(video),
    ], check=True)
    result = await sample_visual_evidence(video, 0.2, 1.5)
    assert result["analysisLevel"] == "three_actual_video_frames"
    assert result["semanticVerified"] is False
    frames = result["frames"]
    assert len(frames) == 3
    assert frames[0]["atSec"] < frames[1]["atSec"] < frames[2]["atSec"]
    for item in frames:
        data = base64.b64decode(item["jpegBase64"], validate=True)
        assert data.startswith(b"\xff\xd8")
        assert len(data) > 100


@pytest.mark.asyncio
async def test_out_of_bounds_refuses_without_fabricating_frames(tmp_path):
    video = tmp_path / "short.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=320x180:d=1.1",
        "-an", "-threads", "1", "-y", str(video)
    ], check=True)
    with pytest.raises(ValueError, match="dépasse"):
        await sample_visual_evidence(video, 0.9, 1.0)

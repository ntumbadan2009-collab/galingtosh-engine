import shutil
import subprocess
import pytest
from pathlib import Path
from app.core.renderer import FilmRenderer

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg/ffprobe requis")

@pytest.mark.asyncio
async def test_render_generated_color_clip(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=red:s=320x180:r=24", "-t", "1", "-pix_fmt", "yuv420p", str(source)], check=True)
    film = {
        "info": {"title": "test"},
        "format": {"aspect": "16:9", "fps": 24},
        "scenes": [{"id": "s1", "order": 1, "durationSec": 1,
                    "shots": [{"id": "p1", "order": 1, "inSec": 0, "outSec": 1,
                               "mediaRef": "m1", "camera": {"type": "none"}}]}],
        "media": [{"id": "m1", "kind": "video"}],
        "render": {"resolution": "720p"}
    }
    result = await FilmRenderer(max_seconds=10, max_output_mb=10).render(film, {"m1": source}, tmp_path / "out.mp4")
    assert Path(result["output"]).is_file()
    assert result["width"] == 1280 and result["height"] == 720
    assert result["audio"] is False

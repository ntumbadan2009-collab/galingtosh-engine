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


@pytest.mark.asyncio
async def test_render_with_audio_subtitles_and_effects(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "voice.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=320x180:r=24", "-t", "2", "-pix_fmt", "yuv420p", str(video)], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", str(audio)], check=True)
    film = {
        "info": {"title": "audiovisuel", "language": "fr"},
        "format": {"aspect": "16:9", "fps": 24},
        "scenes": [{"id": "s1", "order": 1, "durationSec": 2,
                    "shots": [{"id": "p1", "order": 1, "inSec": 0, "outSec": 2,
                               "mediaRef": "video1", "camera": {"type": "none"}}]}],
        "media": [{"id": "video1", "kind": "video"}, {"id": "audio1", "kind": "audio"}],
        "audio": {"tracks": [{"id": "voice", "kind": "voiceover", "mediaRef": "audio1",
                              "events": [{"id": "e1", "startSec": 0, "durationSec": 2}]}]},
        "subtitles": [{"language": "fr", "cues": [{"startSec": 0.2, "endSec": 1.5, "text": "Bonjour."}]}],
        "effects": [{"type": "grayscale", "target": "film", "params": {}}],
        "render": {"resolution": "720p", "audioBitrateKbps": 96}
    }
    result = await FilmRenderer(max_seconds=10, max_output_mb=10).render(
        film, {"video1": video, "audio1": audio}, tmp_path / "final.mp4")
    assert result["audio"] is True
    assert result["subtitles_burned"] is True
    assert result["effects_applied"] == 1


@pytest.mark.asyncio
async def test_french_titles_and_subtitles_together(tmp_path):
    from app.media.effects import build_video_filters, finish_video
    from app.media.subtitles import write_srt
    from app.media.ffmpeg import probe_media
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=24:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True)
    titles = [
        "Graphique : Retrait de la main-d'œuvre 1980-2050 (Projection)",
        "L'avenir : 50%, [2026]; \\ données",
    ]
    effects = [{"type": "text_overlay", "target": "s1", "params": {"text": t}} for t in titles]
    filters, warnings = build_video_filters(effects, 2, 320, 180, {"s1": (0, 2)},
                                           text_directory=tmp_path)
    assert not warnings
    assert len(filters) == 2
    assert all("textfile=" in f and "expansion=none" in f for f in filters)
    assert (tmp_path / "overlay_0000.txt").read_text(encoding="utf-8") == titles[0]
    subtitles = tmp_path / "captions.srt"
    assert write_srt([{"language": "fr", "cues": [
        {"startSec": 0.2, "endSec": 1.8, "text": "L'évolution de la population."}
    ]}], subtitles, "fr")
    await finish_video(source, output, filters, subtitles)
    assert output.is_file()
    assert float((await probe_media(str(output)))["format"]["duration"]) >= 1.9

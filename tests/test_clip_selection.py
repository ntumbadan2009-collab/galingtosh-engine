"""Tests for actual shot inspection and reviewed temporal selection."""
import shutil
import subprocess
from pathlib import Path

import pytest

from app.media.clip_selection import inspect_video_passages, choose_reviewed_passage

FFMPEG_READY = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def test_reviewed_selection_rejects_missing_semantic_evidence():
    candidates = [
        {"startSec": 0.0, "endSec": 3.0, "semanticVerified": False},
        {"startSec": 3.0, "endSec": 6.0, "semanticVerified": False},
    ]
    assert choose_reviewed_passage(candidates, []) is None
    assert choose_reviewed_passage(candidates, [
        {"candidateIndex": 0, "relevance": 0.1, "visualQuality": 1.0}
    ]) is None
    selected = choose_reviewed_passage(candidates, [
        {"candidateIndex": 0, "relevance": 0.75, "visualQuality": 0.9},
        {"candidateIndex": 1, "relevance": 0.93, "visualQuality": 0.9},
    ])
    assert selected["candidateIndex"] == 1
    assert selected["startSec"] == 3.0
    assert selected["semanticVerified"] is True


def test_reviewed_selection_rejects_invalid_scores():
    candidates = [{"startSec": 0.0, "endSec": 4.0}]
    assert choose_reviewed_passage(candidates, [
        {"candidateIndex": 0, "relevance": float("nan"), "visualQuality": 1}
    ]) is None
    assert choose_reviewed_passage(candidates, [
        {"candidateIndex": 0, "relevance": 0.95, "visualQuality": 0.1}
    ]) is None


@pytest.mark.skipif(not FFMPEG_READY, reason="FFmpeg requis")
@pytest.mark.asyncio
async def test_detects_real_visual_cut(tmp_path: Path):
    source = tmp_path / "cut.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=320x180:r=24:d=1",
        "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=24:d=1",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(source),
    ], check=True)
    result = await inspect_video_passages(
        source, min_clip_seconds=0.5, max_clip_seconds=8,
        scene_threshold=0.20,
    )
    assert result["analysisLevel"] == "shot_boundaries_only"
    assert result["requiresSemanticReview"] is True
    assert any(0.75 < c["endSec"] < 1.25 for c in result["candidates"])
    assert all(c["semanticVerified"] is False for c in result["candidates"])


@pytest.mark.skipif(not FFMPEG_READY, reason="FFmpeg requis")
@pytest.mark.asyncio
async def test_renderer_respects_source_in_second(tmp_path: Path, monkeypatch):
    from app.core.renderer import FilmRenderer
    import app.core.renderer as renderer_module

    source = tmp_path / "timeline.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=160x90:r=24:d=1",
        "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=1",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(source),
    ], check=True)
    seen = []
    original = renderer_module.normalize_video

    async def capture(src, dest, width, height, fps, start, duration, camera):
        seen.append(start)
        await original(src, dest, width, height, fps, start, duration, camera)

    monkeypatch.setattr(renderer_module, "normalize_video", capture)
    film = {
        "info": {"title": "test"},
        "format": {"aspect": "16:9", "fps": 24},
        "scenes": [{"id": "scene", "order": 1, "durationSec": 0.5,
                    "shots": [{"id": "shot", "order": 1, "inSec": 0,
                               "outSec": 0.5, "sourceInSec": 1,
                               "mediaRef": "video", "camera": {"type": "none"}}]}],
        "media": [{"id": "video", "kind": "video"}],
        "render": {"resolution": "720p"},
    }
    await FilmRenderer(max_seconds=10, max_output_mb=15).render(
        film, {"video": source}, tmp_path / "result.mp4"
    )
    assert seen == [1.0]


@pytest.mark.skipif(not FFMPEG_READY, reason="FFmpeg requis")
@pytest.mark.asyncio
async def test_rejects_video_source_range_past_end(tmp_path: Path):
    from app.media.video import normalize_video
    from app.media.ffmpeg import FFmpegError

    source = tmp_path / "one_second.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=160x90:r=24:d=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ], check=True)
    with pytest.raises(FFmpegError, match="hors de la vidéo"):
        await normalize_video(source, tmp_path / "out.mp4", 320, 180, 24,
                              0.8, 0.6)

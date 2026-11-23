"""Oversized MP4 handling protects narration and validates the output."""
import pytest
from app.media import compression
from app.media.ffmpeg import FFmpegError


@pytest.mark.asyncio
async def test_oversized_video_recompressed_without_losing_audio(monkeypatch, tmp_path):
    source = tmp_path / "final.mp4"
    source.write_bytes(b"x" * 1200000)
    calls = []

    async def fake_run_ffmpeg(args, *, timeout):
        calls.append(args)
        destination = args[-1]
        from pathlib import Path
        Path(destination).write_bytes(b"z" * 190000)

    async def fake_probe(path):
        return {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
                "format": {"duration": "18.0"}}

    monkeypatch.setattr(compression, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(compression, "probe_media", fake_probe)
    report = await compression.fit_mp4_to_limit(source, 1, audio_bitrate_kbps=128)
    assert report["recompressed"]
    assert report["size_after_mb"] < 1
    assert source.stat().st_size == 190000
    assert "-c:a" in calls[0]
    assert calls[0][calls[0].index("-c:a") + 1] == "copy"
    assert "-map" in calls[0]
    assert not list(tmp_path.glob("*.compact-*.mp4"))


@pytest.mark.asyncio
async def test_small_video_skips_encoding(monkeypatch, tmp_path):
    source = tmp_path / "small.mp4"
    source.write_bytes(b"x" * 5000)
    async def should_not_run(*args, **kwargs):
        raise AssertionError("unnecessary transcode")
    monkeypatch.setattr(compression, "run_ffmpeg", should_not_run)
    result = await compression.fit_mp4_to_limit(source, 1)
    assert not result["recompressed"]


@pytest.mark.asyncio
async def test_failed_compression_keeps_original(monkeypatch, tmp_path):
    source = tmp_path / "oversized.mp4"
    source.write_bytes(b"x" * 1200000)
    async def fake_run_ffmpeg(args, *, timeout):
        from pathlib import Path
        Path(args[-1]).write_bytes(b"y" * 1200000)
    async def fake_probe(path):
        return {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
                "format": {"duration": "18.0"}}
    monkeypatch.setattr(compression, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(compression, "probe_media", fake_probe)
    with pytest.raises(FFmpegError, match="Impossible de réduire"):
        await compression.fit_mp4_to_limit(source, 1)
    assert source.stat().st_size == 1200000
    assert not list(tmp_path.glob("*.compact-*.mp4"))

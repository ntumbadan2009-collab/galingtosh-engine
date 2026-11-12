import pytest
from app.media import audio


@pytest.mark.asyncio
async def test_synthesized_tts_track_is_not_reported_missing(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    voice = tmp_path / "voice.mp3"
    video.write_bytes(b"video")
    voice.write_bytes(b"voice")
    calls = []

    async def fake_ffmpeg(args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(audio, "run_ffmpeg", fake_ffmpeg)
    has_audio, warnings = await audio.mix_audio(
        video,
        [{"id": "narration", "kind": "voiceover", "tts": {"provider": "edge-tts"},
          "mediaRef": "narration"}],
        {"narration": voice},
        tmp_path / "final.mp4",
        8.0,
    )

    assert has_audio is True
    assert warnings == []
    assert calls


@pytest.mark.asyncio
async def test_failed_tts_track_has_specific_warning(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    has_audio, warnings = await audio.mix_audio(
        video,
        [{"id": "narration", "kind": "voiceover", "tts": {"provider": "edge-tts"}}],
        {},
        tmp_path / "final.mp4",
        8.0,
    )

    assert has_audio is False
    assert any("Voix TTS indisponible" in warning for warning in warnings)

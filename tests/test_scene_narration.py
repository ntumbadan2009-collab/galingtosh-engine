import pytest

from app.core.narration import align_scene_narrations
from app.media.tts import synthesize_scene_narrations


def test_scene_narrations_are_independent_and_use_measured_offsets():
    film = {"scenes": [
        {"id": "s1", "order": 1, "durationSec": 10, "shots": [{"inSec": 0, "outSec": 10}],
         "narration": {"targetDurationSec": 10}},
        {"id": "s2", "order": 2, "durationSec": 20, "shots": [{"inSec": 0, "outSec": 20}],
         "narration": {"targetDurationSec": 20}},
    ]}
    film["subtitles"] = [{"cues": [
        {"startSec": 5, "endSec": 10, "text": "Fin scène 1"},
        {"startSec": 10, "endSec": 20, "text": "Scène 2"},
    ]}]
    tracks, warnings = align_scene_narrations(film, {"s1": 8.5, "s2": 23})
    assert [scene["durationSec"] for scene in film["scenes"]] == [8.5, 23]
    assert [track["events"][0]["startSec"] for track in tracks] == [0, 8.5]
    assert [track["events"][0]["durationSec"] for track in tracks] == [8.5, 23]
    assert film["scenes"][0]["shots"][0]["outSec"] == 8.5
    assert film["subtitles"][0]["cues"][0]["endSec"] == 8.5
    assert film["subtitles"][0]["cues"][1]["startSec"] == 8.5
    assert film["subtitles"][0]["cues"][1]["endSec"] == 20.0
    assert len(warnings) == 2


@pytest.mark.asyncio
async def test_scene_tts_synthesizes_one_file_per_scene(tmp_path, monkeypatch):
    async def fake_synthesize(text, language, voice, destination):
        destination.write_bytes(b"audio")
        return 3.25 if text == "Texte un" else 6.5

    monkeypatch.setattr("app.media.tts.synthesize_text", fake_synthesize)
    film = {"info": {"language": "fr"}, "scenes": [
        {"id": "one", "order": 1, "narration": {"text": "Texte un"}},
        {"id": "two", "order": 2, "narration": {"text": "Texte deux"}},
    ]}
    files, durations, warnings = await synthesize_scene_narrations(film, tmp_path)
    assert not warnings
    assert set(files) == {"__scene_narration_one", "__scene_narration_two"}
    assert durations == {"one": 3.25, "two": 6.5}
    assert all(path.is_file() for path in files.values())

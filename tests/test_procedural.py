import wave

from app.media.procedural import MIDI_CHORDS, compose_bed, synthesize_effect


def test_scene_music_uses_supported_midi_note_chords(tmp_path):
    assert set(MIDI_CHORDS) == {"calm", "hopeful", "tense", "sad", "wonder", "neutral"}
    assert all(all(isinstance(note, int) and 0 <= note <= 127 for note in chord) for chord in MIDI_CHORDS.values())
    output = tmp_path / "music.wav"
    assert compose_bed([{"id": "scene-1", "durationSec": 1}],
                       [{"sceneId": "scene-1", "mood": "calm", "intensity": .3}], output)
    with wave.open(str(output), "rb") as audio:
        assert audio.getframerate() == 16000
        assert audio.getnframes() == 16000


def test_effects_are_synthesized_and_unsupported_sounds_are_omitted(tmp_path):
    output = tmp_path / "steps.wav"
    assert synthesize_effect("pas de marche", output, .5)
    with wave.open(str(output), "rb") as audio:
        assert audio.getnframes() == 8000
    unsupported = tmp_path / "unsupported.wav"
    assert not synthesize_effect("explosion réaliste avec foule", unsupported, .5)
    assert not unsupported.exists()

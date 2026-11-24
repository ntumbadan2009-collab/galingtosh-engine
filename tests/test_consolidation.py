import pytest
from app.media.procedural import classify_effect
from app.media.tts import voice_direction

def test_no_false_positive_sound_labels():
    for text in ("pas de musique", "pas de pluie", "ventilateur", "un passant", "un coup de vent", "explosion puis impact"):
        assert classify_effect(text) is None
    assert classify_effect("Pas de marche")=="steps"
    assert classify_effect("bruit de vent")=="wind"

def test_voice_direction_validation():
    assert voice_direction(-12,4)==(-12,4)
    for rate,pitch in [(True,0),(21,0),(0,-13),(1.5,0)]:
        with pytest.raises(ValueError):
            voice_direction(rate,pitch)

import pytest
from app.core.validator import validate_film

def test_rejects_non_finite_scene_duration():
    film={"format":{"aspect":"16:9"},"scenes":[{"durationSec":float("nan"),"shots":[]}]}
    assert validate_film(film)["valid"] is False

def test_rejects_unhashable_shot_id_without_crashing():
    film={"format":{"aspect":"16:9"},"scenes":[{"durationSec":2,"shots":[{"id":[],"inSec":0,"outSec":1}]}]}
    assert validate_film(film)["valid"] is False

def test_rejects_empty_film():
    assert validate_film({"format":{"aspect":"16:9"},"scenes":[]})["valid"] is False

from app.core.validator import validate_film

def base_film():
    return {"format": {"aspect": "16:9", "fps": 24}, "scenes": [
        {"durationSec": 5, "shots": [{"id": "p1", "inSec": 0, "outSec": 6, "camera": {"type": "mystery"}}]}
    ]}

def test_valid_film_reports_degraded_features_as_warnings():
    result = validate_film(base_film())
    assert result["valid"] is True
    assert any("tronqué" in warning for warning in result["warnings"])
    assert any("Caméra" in warning for warning in result["warnings"])

def test_missing_aspect_is_blocking():
    result = validate_film({"format": {}, "scenes": []})
    assert result["valid"] is False
    assert result["errors"]

def test_3d_media_is_explicitly_warned():
    film = base_film()
    film["media"] = [{"kind": "model3d"}]
    assert any("3D" in w for w in validate_film(film)["warnings"])

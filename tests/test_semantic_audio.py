from app.media.semantic_audio import compare_audio
from app.media.procedural import synthesize_effect


def test_clap_requires_winner_and_margin(tmp_path, monkeypatch):
    clip = tmp_path / "candidate.wav"
    clip.write_bytes(b"test")
    class Fake:
        def __call__(self, path, **kwargs):
            expected = kwargs["candidate_labels"][0]
            return [{"label": expected, "score": .82}, {"label": "music", "score": .08}]
    monkeypatch.setattr("app.media.semantic_audio._load_classifier", lambda: Fake())
    assert compare_audio(clip, "rain falling")["status"] == "confirmed"


def test_clap_rejects_ambiguous_candidate(tmp_path, monkeypatch):
    clip = tmp_path / "candidate.wav"
    clip.write_bytes(b"test")
    class Fake:
        def __call__(self, path, **kwargs):
            labels = kwargs["candidate_labels"]
            return [{"label": labels[0], "score": .43}, {"label": "unrelated ambient sound", "score": .4}]
    monkeypatch.setattr("app.media.semantic_audio._load_classifier", lambda: Fake())
    assert compare_audio(clip, "rain falling")["status"] == "rejected"


def test_procedural_effect_only_supports_known_categories(tmp_path):
    assert synthesize_effect("footsteps on gravel", tmp_path / "steps.wav", .5)
    assert (tmp_path / "steps.wav").stat().st_size > 1000
    assert not synthesize_effect("volcano eruption with crowd", tmp_path / "unknown.wav", .5)

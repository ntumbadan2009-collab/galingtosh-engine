"""Fail-closed examples for narrative relevancy and code-first video."""
import shutil
from pathlib import Path

import pytest
from PIL import Image

from app.core.narrative_policy import narrative_issues, excerpt_matches
from app.media.narrative_cards import render_code_card

NARRATION = "L'intelligence artificielle analyse des milliers de documents. Mais certaines réponses peuvent être fausses."


def film_with(*shots, media=None):
    return {
        "info": {"title": "test", "language": "fr", "visualPolicy": "strict"},
        "format": {"aspect": "16:9", "fps": 24},
        "render": {"resolution": "720p"},
        "media": media or [],
        "scenes": [{
            "id": "s1", "order": 1, "durationSec": 8,
            "title": "Comprendre les limites",
            "narration": {"text": NARRATION},
            "shots": list(shots),
        }],
    }


def code_shot(text="L'intelligence artificielle analyse des milliers de documents.", duration=8):
    return {
        "id": "p1", "order": 1, "inSec": 0, "outSec": duration,
        "visualMode": "programmatic", "visualText": text,
        "cardStyle": "focus",
    }


def evidence(quote="Mais certaines réponses peuvent être fausses.", kind="image"):
    samples = [{
        "description": "Un écran d'ordinateur avec un avertissement lisible.",
        "relevance": 0.91, "visualQuality": 0.81,
        "hasContradiction": False,
    }]
    if kind == "video":
        samples = [{**samples[0], "atSec": t} for t in (0.5, 2.5, 4.5)]
    return {
        "verifiedBy": "vision_observation_v1", "actualVisualAnalysis": True,
        "mediaRef": "m1", "narrationQuote": quote,
        "visualIntent": "Un avertissement de réponse inexacte sur l'écran",
        "hasContradiction": False, "licenseChecked": True,
        "sourceInSec": 0, "samples": samples,
    }


def test_exact_quote_allowed_but_unrelated_or_made_up_text_rejected():
    assert excerpt_matches(NARRATION, "artificielle analyse des milliers")
    assert not excerpt_matches(NARRATION, "Une IA a obtenu 99 % de réussite.")
    assert not narrative_issues(film_with(code_shot()))
    assert narrative_issues(film_with(code_shot("Un robot inventé dans un hôpital.")))


def test_code_cards_cannot_hide_long_static_slides():
    assert any("trop longue" in item for item in narrative_issues(film_with(code_shot(duration=18))))


def test_unreviewed_stock_media_is_never_implicitly_accepted():
    media = [{"id": "m1", "kind": "image", "source": "search"}]
    shot = {"id": "p1", "order": 1, "inSec": 0, "outSec": 8, "mediaRef": "m1"}
    assert narrative_issues(film_with(shot, media=media))


def test_real_image_requires_quote_license_and_positive_samples():
    m = [{"id": "m1", "kind": "image", "source": "search"}]
    shot = {"id": "p1", "order": 1, "inSec": 0, "outSec": 8, "mediaRef": "m1",
            "visualMode": "media", "visualEvidence": evidence()}
    assert not narrative_issues(film_with(shot, media=m))
    shot["visualEvidence"]["licenseChecked"] = False
    assert narrative_issues(film_with(shot, media=m))
    shot["visualEvidence"]["licenseChecked"] = True
    shot["visualEvidence"]["samples"][0]["relevance"] = 0.4
    assert narrative_issues(film_with(shot, media=m))


def test_three_distinct_real_video_frames_and_correct_timestamps_required():
    m = [{"id": "m1", "kind": "video", "source": "search"}]
    shot = {"id": "p1", "order": 1, "inSec": 0, "outSec": 8,
            "mediaRef": "m1", "sourceInSec": 0,
            "visualEvidence": evidence(kind="video")}
    assert not narrative_issues(film_with(shot, media=m))
    shot["sourceInSec"] = 4
    assert narrative_issues(film_with(shot, media=m))
    shot["sourceInSec"] = 0
    shot["visualEvidence"]["samples"].pop()
    assert narrative_issues(film_with(shot, media=m))


def test_programmatic_card_is_readable_and_never_uses_external_images(tmp_path):
    png = tmp_path / "scripted.png"
    render_code_card(png, narration_quote=NARRATION[:63],
                     scene_title="Dangers de l'IA", scene_number=2,
                     width=1280, height=720, style="question")
    with Image.open(png) as im:
        assert im.size == (1280, 720)
        assert im.getpixel((50, 50)) != im.getpixel((100, 120))  # deterministic accent stripe


@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg requis")
async def test_strict_code_shot_produces_a_real_video(tmp_path):
    from app.core.renderer import FilmRenderer
    film = film_with(code_shot(duration=1))
    film["scenes"][0]["durationSec"] = 1
    output = tmp_path / "narrative.mp4"
    result = await FilmRenderer(max_seconds=10, max_output_mb=10).render(film, {}, output)
    assert output.is_file() and output.stat().st_size > 2000
    assert 0.9 <= result["duration_seconds"] <= 1.5


@pytest.mark.asyncio
async def test_strict_renderer_refuses_unproven_stock_footage(tmp_path):
    from app.core.renderer import FilmRenderer, RenderError
    film = film_with(
        {"id":"p1","order":1,"inSec":0,"outSec":8,"mediaRef":"unknown"},
    )
    with pytest.raises(RenderError, match="preuves visuelles"):
        await FilmRenderer(max_seconds=10, max_output_mb=10).render(film, {}, tmp_path/"invalid.mp4")

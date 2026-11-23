"""Level-2 code-only visual diagrams: narrative faithfulness and FFmpeg output."""
import shutil
from PIL import Image, ImageChops
import pytest

from app.core.motion_policy import motion_spec_issues
from app.core.narrative_policy import narrative_issues
from app.media.motion_graphics import render_motion_frames, render_motion_graphic

STORY = ("Le moteur collecte les documents, puis il les vérifie "
         "et ensuite il prépare une synthèse claire.")
STEPS = ["Le moteur collecte les documents", "puis il les vérifie",
         "ensuite il prépare une synthèse claire"]
TIME = "En 2020, nous préparons le prototype, puis en 2022 nous testons le système."
TIMELINE = ["En 2020, nous préparons le prototype", "puis en 2022 nous testons le système"]
CONTRAST = "Un premier choix réduit les étapes, mais un deuxième choix demande davantage de contrôle."
COMPARE = ["Un premier choix réduit les étapes", "mais un deuxième choix demande davantage de contrôle"]


def shot(spec,quote=STORY,duration=4):
    return {"id":"m1","order":1,"inSec":0,"outSec":duration,"visualMode":"programmatic",
            "visualText":quote,"visualSpec":spec}


def film(shot_,quote=STORY):
    return {"info":{"visualPolicy":"strict","title":"Tests motion"},
        "format":{"aspect":"16:9","fps":24},"render":{"resolution":"720p"},
        "scenes":[{"id":"scene-1","title":"Explication","durationSec":shot_["outSec"],
                   "order":1,"narration":{"text":quote},"shots":[shot_]}],"media":[]}


def test_strict_ordered_quotes_and_no_fabricated_nodes():
    correct={"type":"steps","items":[{"text":s} for s in STEPS]}
    assert not motion_spec_issues(STORY,STORY,correct)
    assert not narrative_issues(film(shot(correct)))
    assert motion_spec_issues(STORY,STORY,{"type":"steps",
        "items":[{"text":STEPS[1]},{"text":STEPS[0]}]})
    assert motion_spec_issues(STORY,STORY,{"type":"steps",
        "items":[{"text":"200 % des documents"},{"text":STEPS[0]}]})
    assert motion_spec_issues(STORY,STORY,{"type":"steps",
        "items":[{"text":STEPS[0],"imaginedDate":"2030"},{"text":STEPS[1]}]})


def test_comparison_and_timeline_require_explicit_rhetoric():
    assert not motion_spec_issues(TIME,TIME,{"type":"timeline",
        "items":[{"text":t} for t in TIMELINE]})
    assert not motion_spec_issues(CONTRAST,CONTRAST,{"type":"comparison",
        "items":[{"text":t} for t in COMPARE]})
    assert motion_spec_issues(STORY,STORY,{"type":"timeline",
        "items":[{"text":STEPS[0]},{"text":STEPS[1]}]}) == []  # Explicit "puis"
    plain="Le jardin contient des roses et le bâtiment contient des fenêtres."
    assert motion_spec_issues(plain,plain,{"type":"timeline",
        "items":[{"text":"Le jardin contient des roses"},{"text":"et le bâtiment contient des fenêtres"}]})
    assert motion_spec_issues(plain,plain,{"type":"comparison",
        "items":[{"text":"Le jardin contient des roses"},{"text":"et le bâtiment contient des fenêtres"}]})


def test_invalid_specs_rejected_before_render():
    bad={"type":"comparison","items":[{"text":STEPS[0]}]}
    assert narrative_issues(film(shot(bad)))
    assert motion_spec_issues(STORY,STORY,{"type":["steps"],"items":[]})
    assert motion_spec_issues(STORY,STORY,{"type":"focus",
        "items":[{"text":"Ceci est ajouté et n'existe pas dans le récit."}]})


def test_landscape_and_portrait_frames_reveal_information_progressively(tmp_path):
    layouts=[
        (640,360,{"type":"steps","items":[{"text":s} for s in STEPS]}),
        (360,640,{"type":"comparison","items":[{"text":s} for s in COMPARE]}),
    ]
    for i,(w,h,spec) in enumerate(layouts):
        folder=tmp_path/f"frames_{i}"
        n=render_motion_frames(folder,spec=spec,scene_title="Vérification",
            scene_number=2,width=w,height=h,duration=3)
        assert n == 24
        with Image.open(folder/"frame_0000.png") as first, Image.open(folder/"frame_0023.png") as last:
            assert first.size==(w,h)
            assert ImageChops.difference(first,last).getbbox() is not None


@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which("ffmpeg"),reason="FFmpeg non disponible")
async def test_real_motion_graphic_encoded_without_stock_media(tmp_path):
    from app.core.renderer import FilmRenderer
    graphic={"type":"steps","items":[{"text":s} for s in STEPS]}
    output=tmp_path/"animated_explanation.mp4"
    result=await FilmRenderer(max_seconds=10,max_output_mb=10).render(
        film(shot(graphic,duration=3)),{},output)
    assert output.exists() and output.stat().st_size>2000
    assert 2.9<=result["duration_seconds"]<=3.2
    assert result["width"]==1280 and result["height"]==720

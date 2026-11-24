from PIL import Image,ImageChops
from app.media.subtitles import _caption_chunks,write_srt
from app.media.narrative_cards import render_code_card,PALETTES
from app.media.motion_graphics import render_motion_frames,PALETTE

def test_caption_splitting_never_drops_words(tmp_path):
    text="Une observation commence par une question. On regarde ensuite les détails qui peuvent réellement changer notre compréhension des résultats."
    for w,h in [(1280,720),(720,1280)]:
        chunks=_caption_chunks(text,w,h)
        assert " ".join(" ".join(x.split()) for x in chunks)==text
        assert all(len(x.splitlines())<=2 for x in chunks)
        assert write_srt([{"language":"fr","cues":[{"startSec":0,"endSec":9,"text":text}]}],tmp_path/"captions.srt","fr",width=w,height=h)

def test_procedural_images_reserve_caption_band(tmp_path):
    quote="Le cube tourne autour de son axe."
    for w,h in [(1280,720),(720,1280)]:
        p=tmp_path/"card.png"
        render_code_card(p,narration_quote=quote,scene_title="Géométrie",scene_number=1,width=w,height=h,caption_safe=True)
        with Image.open(p) as im:
            assert im.size==(w,h)
            crop=im.crop((0,round(h*.75),w,h))
            assert ImageChops.difference(crop,Image.new("RGB",crop.size,PALETTES["focus"][0])).getbbox() is None
        folder=tmp_path/f"frames_{w}"
        render_motion_frames(folder,spec={"type":"cube_rotation","items":[{"text":quote}]},scene_title="Géométrie",scene_number=1,width=w,height=h,duration=1,caption_safe=True)
        with Image.open(folder/"frame_0004.png") as im:
            crop=im.crop((0,round(h*.75),w,h))
            assert im.size==(w,h)
            assert ImageChops.difference(crop,Image.new("RGB",crop.size,PALETTE["cube_rotation"][0])).getbbox() is None

from app.media.editorial_motion import accent_events, render_accents, zoom_filter
from app.core.motion_policy import motion_spec_issues
import wave

def film():
    return {"scenes":[{"durationSec":10,"shots":[{"id":"a","inSec":0,"outSec":5,"camera":{"type":"zoom_in"}},{"id":"b","inSec":5,"outSec":10,"camera":{"type":"zoom_out"}}]}],"audio":{"tracks":[]}}

def test_synchronized_accents_and_manual_priority(tmp_path):
    f=film()
    events=accent_events(f)
    assert [e["startSec"] for e in events]==[0,5]
    out=tmp_path/"accents.wav"
    render_accents(events,10,out)
    with wave.open(str(out)) as w:
        assert w.getnframes()==160000
        assert any(w.readframes(8000))
        w.setpos(16000)
        assert not any(w.readframes(16000))
    f["audio"]["tracks"]=[{"kind":"sfx","events":[{"startSec":0,"durationSec":1}]}]
    assert [e["startSec"] for e in accent_events(f)]==[5]
    f["audio"]["editorialAccents"]=False
    assert not accent_events(f)

def test_zoom_centred_and_duration_aware():
    assert "on/119" in zoom_filter("zoom_in",640,360,24,5)
    assert "(iw-iw/zoom)/2" in zoom_filter("zoom_out",640,360,24,5)

def test_causality_requires_explicit_language():
    quote="La chaleur provoque une dilatation du métal."
    spec={"type":"cause_effect","items":[{"text":"La chaleur"},{"text":"une dilatation du métal"}]}
    assert not motion_spec_issues(quote,quote,spec)
    quote="La chaleur et une dilatation du métal."
    assert motion_spec_issues(quote,quote,spec)


import shutil
import pytest
from PIL import Image, ImageDraw, ImageChops
from app.media.images import normalize_image
from app.media.video import normalize_video
from app.media.audio import mix_audio
from app.media.ffmpeg import run_ffmpeg, probe_media

@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="FFmpeg absent")
async def test_actual_zoom_and_sound_are_encoded(tmp_path):
    image=tmp_path/"grid.png"
    canvas=Image.new("RGB",(640,360),"#40506a")
    d=ImageDraw.Draw(canvas)
    d.rectangle((120,80,520,280),outline="white",width=7)
    d.ellipse((260,120,380,240),fill="orange")
    canvas.save(image)
    static=tmp_path/"static.mp4"
    await normalize_image(image,static,640,360,24,5,"none")
    moved=tmp_path/"moved.mp4"
    await normalize_video(static,moved,640,360,24,0,5,"zoom_in")
    first,last=tmp_path/"first.png",tmp_path/"last.png"
    for t,dest in [(0,first),(4.75,last)]:
        await run_ffmpeg(["-ss",str(t),"-i",str(moved),"-frames:v","1",str(dest)])
    with Image.open(first) as a,Image.open(last) as b:
        assert ImageChops.difference(a.convert("RGB"),b.convert("RGB")).getbbox()
    audio=tmp_path/"accents.wav"
    render_accents([{"startSec":0,"durationSec":.55}],5,audio)
    output=tmp_path/"finished.mp4"
    mixed,warnings=await mix_audio(moved,[{"kind":"sfx","mediaRef":"fx","volumeDb":-10}],{"fx":audio},output,5,editorial=True)
    assert mixed and not warnings
    probe=await probe_media(str(output))
    assert any(s.get("codec_type")=="audio" for s in probe["streams"])
    assert abs(float(probe["format"]["duration"])-5)<.2

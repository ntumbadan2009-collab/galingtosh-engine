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

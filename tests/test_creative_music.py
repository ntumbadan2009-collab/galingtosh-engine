import wave
from app.media.creative_music import compose_score,RATE

def test_original_score_is_deterministic_and_respects_silence(tmp_path):
    scenes=[{"id":"a","durationSec":1.25},{"id":"b","durationSec":.75},{"id":"c","durationSec":1.5}]
    cues=[{"sceneId":"a","mood":"hopeful","intensity":.7},{"sceneId":"b","mood":"silence","intensity":1},{"sceneId":"c","mood":"tense","intensity":.5}]
    a,b=tmp_path/"a.wav",tmp_path/"b.wav"
    assert compose_score(scenes,cues,a) and compose_score(scenes,cues,b)
    assert a.read_bytes()==b.read_bytes()
    with wave.open(str(a)) as w:
        assert w.getnchannels()==2 and w.getnframes()==round(3.5*RATE)
        assert any(w.readframes(round(1.25*RATE)))
        assert not any(w.readframes(round(2*RATE)-round(1.25*RATE)))
        assert any(w.readframes(round(1.5*RATE)))
    assert not compose_score(scenes,[{"sceneId":"a","mood":"silence","intensity":1}],tmp_path/"none.wav")

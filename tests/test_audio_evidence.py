import pytest
from app.media.audio_evidence import licensed_public_sound,extract_audio_clip,prepare_verified_sound
from app.media.ffmpeg import run_ffmpeg

def media():
 return {"id":"sound","kind":"audio","source":"search","provenance":{"source":"wikimedia","license_url":"https://creativecommons.org/licenses/by/4.0/","author":"Test fixture","attribution":"Test fixture CC BY","url":"https://commons.wikimedia.org/wiki/File:Test.ogg","download_url":"https://upload.wikimedia.org/test.ogg"}}

def test_sound_license_policy():
 m=media();assert licensed_public_sound(m)
 for url in ["https://creativecommons.org/licenses/by-nc/4.0/","https://creativecommons.org.evil.example/licenses/by/4.0/","https://creativecommons.org/licenses/by-sa/4.0/"]:
  m["provenance"]["license_url"]=url
  assert not licensed_public_sound(m)
 m=media();m["provenance"]["source"]="freesound";assert not licensed_public_sound(m)

@pytest.mark.asyncio
async def test_extract_and_bind_audio_bytes_and_timeline(tmp_path):
 source=tmp_path/"synthetic_test_tone.wav";target=tmp_path/"clip.wav"
 await run_ffmpeg(["-f","lavfi","-i","sine=frequency=800:duration=2",str(source)])
 sample=await extract_audio_clip(source,.2,.5,target)
 assert sample["audioBase64"].startswith("UklGR") and len(sample["sourceSha256"])==64
 quote="Un signal sonore retentit."
 # Mock semantic evidence solely to test integrity, not to claim a model heard this test tone.
 evidence={"verifiedBy":"gemini_audio_observation_v1","actualAudioAnalysis":True,"match":"pass","containsSpeech":False,"containsMusic":False,"mediaRef":"sound","shotId":"s","expectedContent":"signal sonore","narrationQuote":quote,"sourceSha256":sample["sourceSha256"],"sourceInSec":.2,"durationSec":.5,"offsetSec":.25}
 track={"mediaRef":"sound","expectedContent":"signal sonore","soundEvidence":evidence}
 film={"media":[media()],"scenes":[{"durationSec":2,"narration":{"text":quote},"shots":[{"id":"s","visualMode":"programmatic","visualText":quote,"inSec":0,"outSec":2}]}]}
 await prepare_verified_sound(film,track,source,target)
 assert track["events"]==[{"startSec":.25,"durationSec":.5}]
 evidence["sourceSha256"]="0"*64
 with pytest.raises(ValueError,match="changé"):await prepare_verified_sound(film,track,source,target)

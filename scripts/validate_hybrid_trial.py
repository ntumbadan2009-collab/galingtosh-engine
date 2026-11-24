"""Network-dependent demonstration fixture; NOT a production source verifier.

Uses a published NASA photo, preselected by the developer, and fixture-only
visual evidence to exercise the strict rendering path. No semantic-model
review is claimed. Requires actual downloaded photo bytes and offline speech.
"""
import asyncio
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image
from app.core.variant_trials import render_trial
from app.media.ffmpeg import run_ffmpeg,probe_media
from app.media.resolver import download_public_media

PHOTO_PAGE="https://eol.jsc.nasa.gov/Collections/EarthFromSpace/images.pl?photo=AS17-148-22727"
PHOTO_URL="https://eol.jsc.nasa.gov/DatabaseImages/EFS/lowres/AS17/AS17-148-22727.JPG"
ORIGINAL_URL="https://eol.jsc.nasa.gov/DatabaseImages/scanned/highres/AS17/AS17-148-22727.JPG"

async def main(root:Path):
    root.mkdir(parents=True,exist_ok=True)
    photo=root/"earth.jpg"
    try:
        _,mime=await download_public_media(PHOTO_URL,photo,25*1024*1024)
    except (OSError,ValueError,asyncio.TimeoutError):
        _,mime=await download_public_media(ORIGINAL_URL,photo,25*1024*1024)
    if mime!="image/jpeg":raise ValueError("The original photograph could not be downloaded.")
    with Image.open(photo) as im:
        im.verify()
    with Image.open(photo) as im:
        if min(im.size)<480:raise ValueError("Photo too small.")
    photo_hash=hashlib.sha256(photo.read_bytes()).hexdigest()
    quotes=["Voici la Terre photographiée depuis l'espace.","Une sphère tourne autour de son axe."]
    sid="earth_scene";duration=12
    voice_parts=[]
    for i,q in enumerate(quotes):
        raw=root/f"voice_{i}.wav";fitted=root/f"voice_{i}_fit.wav"
        subprocess.run(["espeak-ng","-v","fr","-s","150","-w",str(raw),q],check=True)
        probe=await probe_media(str(raw))
        sec=float(probe["format"]["duration"])
        tempo=max(1,sec/5.7)
        if tempo>2:raise ValueError("Voice too long for fixture.")
        await run_ffmpeg(["-i",str(raw),"-af",f"atempo={tempo:.5f},apad","-t","6","-ar","22050","-ac","1",str(fitted)])
        voice_parts.append(fitted)
    listing=root/"voice_concat.txt"
    listing.write_text("\n".join(f"file '{p.resolve()}'" for p in voice_parts),encoding="utf-8")
    voice=root/"voice.wav"
    await run_ffmpeg(["-f","concat","-safe","0","-i",str(listing),"-c:a","pcm_s16le",str(voice)])
    ref="__scene_narration_"+sid
    a={"info":{"title":"De la photographie au schéma","type":"custom","language":"fr","visualPolicy":"strict","editorialLevel":5},
       "format":{"aspect":"16:9","fps":12},"render":{"resolution":"720p"},
       "scenes":[{"id":sid,"order":1,"title":"La Terre et sa représentation","durationSec":duration,
          "narration":{"text":" ".join(quotes)},"shots":[
            {"id":"photo","order":1,"inSec":0,"outSec":6,"visualMode":"programmatic","visualText":quotes[0],"cardStyle":"focus"},
            {"id":"rotation","order":2,"inSec":6,"outSec":12,"visualMode":"programmatic","visualText":quotes[1],"visualSpec":{"type":"sphere_rotation","items":[{"text":quotes[1]}]}}
          ]}],
       "media":[{"id":"nasa_photo","kind":"image","source":"search","provenance":{"author":"Harrison Schmitt / Apollo 17 / NASA","source":"NASA Johnson Space Center","url":PHOTO_PAGE,"license":"Public domain in the United States (NASA)","attribution":"Apollo 17 / NASA, AS17-148-22727"}}],
       "audio":{"tracks":[{"id":ref,"kind":"voiceover","mediaRef":ref,"events":[{"startSec":0,"durationSec":duration}]}],
         "editorialAccents":False,"proceduralMusic":{"enabled":True,"volumeDb":-18,"cues":[{"sceneId":sid,"mood":"wonder","intensity":.45}]}},
       "subtitles":[{"language":"fr","cues":[{"startSec":i*6+.1,"endSec":i*6+5.8,"text":q} for i,q in enumerate(quotes)]}],
       "transitions":[{"atShotId":"rotation","type":"dissolve","durationSec":.3}],"effects":[]}
    b=copy.deepcopy(a)
    sh=b["scenes"][0]["shots"][0]
    sh.pop("visualText");sh.pop("cardStyle")
    sh.update({"visualMode":"media","mediaRef":"nasa_photo","camera":{"type":"none"},
       # Explicit offline fixture. These numbers exercise the gate, NOT a real model verdict.
       "visualEvidence":{"verifiedBy":"vision_observation_v1","actualVisualAnalysis":True,"mediaRef":"nasa_photo",
         "narrationQuote":quotes[0],"visualIntent":"Photographie historique de la Terre depuis l'espace",
         "hasContradiction":False,"licenseChecked":True,"samples":[{"description":"Fixture d'intégration : image NASA présélectionnée, pas de verdict modèle.",
            "relevance":1,"visualQuality":1,"hasContradiction":False}],"fixtureOnly":True}})
    result=await render_trial(a,b,{"nasa_photo":photo,ref:voice},root/"trial")
    assert result["winner"] is None
    assert all(c["report"]["audio"] and c["report"]["subtitles_burned"] and abs(c["report"]["duration_seconds"]-duration)<.1 for c in result["candidates"])
    assert result["candidates"][0]["sha256"]!=result["candidates"][1]["sha256"]
    assert result["candidates"][0]["audioSha256"] and result["candidates"][0]["audioSha256"]==result["candidates"][1]["audioSha256"]
    meta={"source":PHOTO_PAGE,"credit":"Harrison Schmitt / Apollo 17 / NASA","license":"Public domain in the United States (NASA)","sourceSha256":photo_hash,
          "voice":"offline espeak-ng","visualEvidence":"fixture only; no live model verification","A":"code and geometric animation","B":"actual archival photo and same geometric animation"}
    (root/"trial"/"fixture_provenance.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print(json.dumps({"fixture":meta,"comparison":result},ensure_ascii=False))
if __name__=="__main__":asyncio.run(main(Path(sys.argv[1] if len(sys.argv)>1 else "hybrid-validation")))

"""Offline integration fixture: real 150-second MP4, no secret or paid model."""
import asyncio
import json
import sys
import subprocess
from pathlib import Path
from app.core.renderer import FilmRenderer
from app.core.cinematic_review import collect_review_batches
from app.media.ffmpeg import run_ffmpeg,probe_media

SCENES=[
    ("Observer",["Une observation commence par une question.","On regarde les détails qui peuvent changer notre compréhension.","Puis on décrit ce qui est effectivement visible.","Une interprétation doit rester distincte de cette observation.","Enfin, on formule une hypothèse que l'on pourra tester."]),
    ("Mesurer",["La mesure permet de comparer des observations.","On définit une unité avant de relever les résultats.","On répète ensuite la mesure dans les mêmes conditions.","Les écarts observés sont conservés plutôt que supprimés.","Un résultat doit rester accompagné de ses limites."]),
    ("Comparer",["Une comparaison oppose deux situations précises.","On cherche ce qui est identique dans les deux situations.","Puis on identifie les différences qui peuvent expliquer les écarts.","Une association ne démontre pas nécessairement une cause.","La comparaison oriente les prochaines vérifications."]),
    ("Vérifier",["Une hypothèse doit pouvoir être mise à l'épreuve.","On prépare une méthode que d'autres pourront reproduire.","On vérifie ensuite si les résultats soutiennent l'hypothèse.","Si les résultats divergent, on révise notre explication.","La vérification ne consiste pas à cacher les contradictions."]),
    ("Conclure",["Une conclusion résume ce que l'expérience permet d'affirmer.","On distingue le résultat des questions encore ouvertes.","On décrit ensuite les limites de la méthode utilisée.","Une nouvelle observation peut conduire à une autre hypothèse.","La démarche scientifique reste un travail de vérification."]),
]

async def main(root:Path):
    root.mkdir(parents=True,exist_ok=True)
    film={"info":{"title":"La démarche scientifique","language":"fr","visualPolicy":"strict","editorialLevel":5},
          "format":{"aspect":"16:9","fps":12},"render":{"resolution":"720p","audioBitrateKbps":128},
          "scenes":[],"media":[],"transitions":[],"effects":[],"subtitles":[{"language":"fr","cues":[]}],
          "audio":{"tracks":[],"proceduralMusic":{"enabled":True,"volumeDb":-15,"cues":[]}}}
    files={}
    for i,(title,quotes) in enumerate(SCENES):
        sid=f"scene_{i}"
        scene={"id":sid,"title":title,"order":i+1,"durationSec":30,"narration":{"text":" ".join(quotes)},"shots":[]}
        # Use actual offline speech as test input, not the production voice provider.
        # One sentence per 6-second window, with bounded speed adjustment and padding.
        parts=[]
        for j,quote in enumerate(quotes):
            shot_id=f"shot_{i}_{j}"
            sh={"id":shot_id,"order":j+1,"inSec":6*j,"outSec":6*(j+1),"visualMode":"programmatic","visualText":quote,"camera":{"type":"none"}}
            if j==0:sh["visualSpec"]={"type":"focus","items":[{"text":quote}]}
            scene["shots"].append(sh)
            film["subtitles"][0]["cues"].append({"startSec":i*30+j*6+.1,"endSec":i*30+j*6+5.8,"text":quote})
            if j==2:film["transitions"].append({"type":"zoom","atShotId":shot_id,"durationSec":.3})
            raw=root/f"{shot_id}.wav";part=root/f"{shot_id}_fit.wav"
            subprocess.run(["espeak-ng","-v","fr","-s","155","-w",str(raw),quote],check=True)
            probe=await probe_media(str(raw));seconds=float(probe["format"]["duration"])
            tempo=max(1,seconds/5.8)
            if tempo>2:raise AssertionError("fixture sentence too long")
            await run_ffmpeg(["-i",str(raw),"-af",f"atempo={tempo:.5f},apad","-t","6","-ar","22050","-ac","1",str(part)])
            parts.append(part)
        listing=root/f"{sid}.txt"
        listing.write_text("\n".join(f"file '{p.resolve()}'" for p in parts),encoding="utf-8")
        voice=root/f"{sid}.wav"
        await run_ffmpeg(["-f","concat","-safe","0","-i",str(listing),"-c:a","pcm_s16le",str(voice)])
        ref="__scene_narration_"+sid;files[ref]=voice
        film["audio"]["tracks"].append({"id":ref,"kind":"voiceover","mediaRef":ref,"events":[{"startSec":i*30,"durationSec":30}]})
        film["audio"]["proceduralMusic"]["cues"].append({"sceneId":sid,"mood":["wonder","calm","neutral","tense","hopeful"][i],"intensity":.45})
        film["scenes"].append(scene)
    output=root/"final.mp4"
    result=await FilmRenderer(max_seconds=150,max_output_mb=45).render(film,files,output)
    assert abs(result["duration_seconds"]-150)<=.4
    video=next(s for s in (await probe_media(str(output)))["streams"] if s["codec_type"]=="video")
    assert abs(float(video["duration"])-150)<=.1 and int(video["nb_frames"])==1800
    assert result["audio"] and result["subtitles_burned"] and result["editorial_quality"]["passed"]
    assert result["editorial_quality"]["voice_sources_checked"]==5
    batches=await collect_review_batches(output,film,root/"visual_evidence")
    assert sum(b["count"] for b in batches)==25
    result["fixture"]={"video_stream_seconds":float(video["duration"]),"video_frame_count":int(video["nb_frames"]),"speech":"offline espeak-ng; not production TTS","visual_semantics":"not model-reviewed","shots":25,"evidence_batches":len(batches)}
    (root/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":asyncio.run(main(Path(sys.argv[1] if len(sys.argv)>1 else "long-validation")))

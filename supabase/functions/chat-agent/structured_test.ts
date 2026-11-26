import {repairSceneLayout,sceneVisualReady,chooseCandidate,exactQuote} from "./structured.ts";
import {applyOperation,defaultFilm} from "./film.ts";
const assert=(x:unknown)=>{if(!x)throw Error("Assertion failed");};
function sample(){
 let f=applyOperation(defaultFilm("Test"),"activate_autonomous_level5",{}).film;
 f=applyOperation(f,"add_scene",{title:"Scène",narrativeGoal:"Illustrer",durationSec:9}).film;
 const id=f.scenes[0].id;
 f=applyOperation(f,"set_scene_narration",{scene_id:id,text:"Le guépard traverse la savane. Il accélère sur un terrain dégagé.",targetDurationSec:9}).film;
 return f;
}
Deno.test("broken timeline is repaired once, with exact narration and no gaps",()=>{
 const f=sample(),id=f.scenes[0].id;
 const out=repairSceneLayout(f,id);
 assert(sceneVisualReady(out.film,out.film.scenes[0]));
 assert(out.film.scenes[0].shots.length===2);
 assert(out.film.scenes[0].shots.every((s:any)=>s.outSec-s.inSec<=5&&s.visualMode==="programmatic"));
 assert(repairSceneLayout(out.film,id).changes.length===0);
 assert(f.scenes[0].shots.length===0);
});
Deno.test("candidate selection skips rejected assets and missing licensing",()=>{
 const rows=[{result_id:"bad",license:"CC BY",author:"A",url:"https://example.org",duration:5},{result_id:"unknown",license:"unknown",author:"A",url:"https://example.org"},{result_id:"ok",license:"CC BY",author:"B",url:"https://example.org/2",duration:6}];
 assert(chooseCandidate(rows,new Set(["bad"]),"video",4)?.result_id==="ok");
});
Deno.test("measured target is accepted only by explicit internal alignment",()=>{
 const f=sample(),s=f.scenes[0];
 const next=applyOperation(f,"align_narration_durations",{segments:[{sceneId:s.id,durationSec:9.4,ttsProvider:"edge-tts"}],acceptMeasuredTargets:true}).film;
 assert(next.scenes[0].durationSec===9.4&&next.scenes[0].narration.targetDurationSec===9.4);
});

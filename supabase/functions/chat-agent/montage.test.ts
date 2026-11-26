import {planNarrativeBeats} from "./narrative.ts";
import {applySceneMontage} from "./montage.ts";
import {defaultFilm,applyOperation} from "./film.ts";
const assert=(v:unknown,m:string)=>{if(!v)throw Error(m);};
Deno.test("beats cover 35 seconds with contiguous faithful 5-second shots",()=>{
 const text="La rotation de notre planète change le mouvement de l'atmosphère et des océans. Le rythme du jour et de la nuit est modifié. Des vents puissants affectent les zones côtières.";
 const beats=planNarrativeBeats(text,35);
 assert(beats.length===7,"seven beats");
 assert(beats[0].startSec===0&&beats.at(-1)?.endSec===35,"full coverage");
 assert(beats.every((b,i)=>text.includes(b.quote)&&b.endSec-b.startSec<=5.001&&(!i||beats[i-1].endSec===b.startSec)),"faithful and contiguous");
});
Deno.test("montage applies supported effects but cannot change footage or scope",()=>{
 let film=defaultFilm("Test","custom","fr");
 let out=applyOperation(film,"add_scene",{title:"Scène",narrativeGoal:"Une idée claire",durationSec:4});film=out.film;
 const id=film.scenes[0].id;
 film=applyOperation(film,"set_scene_narration",{scene_id:id,text:"Une idée claire.",targetDurationSec:4}).film;
 film=applyOperation(film,"add_code_shot",{scene_id:id,visualText:"Une idée claire.",inSec:0,outSec:4}).film;
 const sh=film.scenes[0].shots[0];
 const batch={sceneId:id,shotIds:[sh.id],scene:{offset:0}};
 const raw={sceneId:id,decisions:[{shotId:sh.id,camera:"keep",transition:"cut",transitionSeconds:0,effect:"fade_in",sound:"none",soundOffsetSec:0,soundDurationSec:0,reason:"Entrée progressive."}],musicMood:"keep",soundAndSubtitles:"Conserver la voix."};
 const edited=applySceneMontage(film,batch,raw);
 assert(edited.changes.length===1&&edited.film.effects[0].target===sh.id,"real effect");
 assert(edited.film.scenes[0].shots[0].outSec===4&&film.effects.length===0,"immutable input and timing");
 assert(applySceneMontage(edited.film,batch,raw).changes.length===0,"idempotent effect");
 let rejected=false;try{applySceneMontage(film,batch,{...raw,decisions:[{...raw.decisions[0],shotId:"elsewhere"}]});}catch{rejected=true;}
 assert(rejected,"outside scope rejected");
});

import {applyOperation,defaultFilm} from "./film.ts";
import {directProduction} from "./proposal-intents.ts";
const assert=(v:unknown)=>{if(!v)throw Error("Assertion failed");};
Deno.test("explicit creation enters autonomous production",()=>{
 assert(directProduction("Crée une vidéo documentaire de 30 secondes")===30);
 assert(directProduction("Crée une vidéo de 30 secondes sans lancer")===null);
});
Deno.test("unchanged narration preserves voice measurement",()=>{
 const f=applyOperation(defaultFilm("Test"),"add_scene",{title:"Scène",durationSec:4,narrativeGoal:"Test"}).film;
 const s=f.scenes[0];s.narration={text:"Une phrase exacte.",language:"fr",voice:"default",ratePercent:0,pitchHz:0,targetDurationSec:4,measuredDurationSec:4};
 const next=applyOperation(f,"set_scene_narration",{scene_id:s.id,text:s.narration.text,targetDurationSec:4}).film;
 assert(next.scenes[0].narration.measuredDurationSec===4);
});
Deno.test("identical shot bounds do not invalidate visual evidence",()=>{
 const f=applyOperation(defaultFilm("Test"),"add_scene",{title:"Scène",durationSec:4,narrativeGoal:"Test"}).film;
 const s=f.scenes[0];
 const withShot=applyOperation(f,"add_shot",{scene_id:s.id,inSec:0,outSec:4}).film;
 const sh=withShot.scenes[0].shots[0];sh.visualEvidence={test:true};
 assert(applyOperation(withShot,"update_shot",{shot_id:sh.id,inSec:0,outSec:4}).film.scenes[0].shots[0].visualEvidence?.test);
 assert(!applyOperation(withShot,"update_shot",{shot_id:sh.id,outSec:3}).film.scenes[0].shots[0].visualEvidence);
});

import {durationMatches,preflight} from "./production.ts";
function assert(value:boolean,message:string){if(!value)throw Error(message);}
Deno.test("duration matches only actual numeric duration",()=>{
 assert(durationMatches(600,600),"10 minute duration");
 assert(!durationMatches(150,600),"short output must not pass");
 assert(!durationMatches("600",600),"invalid metadata");
});
Deno.test("preflight refuses blank scenes and missing media",()=>{
 assert(preflight({scenes:[]},600)!==null,"empty movie");
 assert(preflight({scenes:[{durationSec:600,shots:[]}]},600)!==null,"missing shots");
 assert(preflight({scenes:[{durationSec:600,shots:[{mediaRef:"a"}]}],media:[]},600)!==null,"missing media");
 assert(preflight({scenes:[{durationSec:600,shots:[{mediaRef:"a"}]}],media:[{id:"a"}]},600)!==null,
   "A file attached by ID is not automatically semantically relevant");
 assert(preflight({scenes:[{durationSec:6,narration:{text:"Une démonstration illustrée fidèlement."},
   shots:[{inSec:0,outSec:6,visualMode:"programmatic",visualText:"Une démonstration illustrée fidèlement."}]}]},6)===null,
   "A code illustration quoting the approved narration is a complete plan");
});

import {missingIntervals,productionGuidance,repairFocus,redundantAttachment} from "./reliability.ts";
import {defaultFilm,applyOperation} from "./film.ts";
Deno.test("focus correction preserves literal quote and strict validation",()=>{
 const f=defaultFilm("Test","custom");
 f.scenes=[{id:"s",order:1,title:"Test",durationSec:5,narration:{text:"Imaginez un instant... Et si la Terre cessait soudainement"},shots:[]}];
 const args={scene_id:"s",inSec:0,outSec:5,visualText:f.scenes[0].narration.text,visualType:"focus",visualItems:["Imaginez un instant...","Et si la Terre cessait soudainement"]};
 const corrected=repairFocus(f,"add_code_shot",args);
 assert(!!corrected.repair&&corrected.args.visualItems.length===1,"repair two fragments");
 assert(applyOperation(f,"add_code_shot",corrected.args).film.scenes[0].shots.length===1,"passes original validator");
 assert(!repairFocus(f,"add_code_shot",{...args,outSec:15}).repair,"do not hide invalid duration");
 assert(!repairFocus(f,"add_code_shot",{...args,visualText:"Un fait inventé."}).repair,"do not invent quote");
 assert(!repairFocus(f,"add_code_shot",{...args,visualType:"comparison"}).repair,"do not change creative type");
 assert(!repairFocus(f,"add_code_shot",{...args,visualItems:["Imaginez un instant..."]}).repair,"valid original remains unchanged");
});
Deno.test("missing coverage is calculated from intervals, not sum or shot count",()=>{
 const s={durationSec:20,shots:[{inSec:0,outSec:5},{inSec:3,outSec:8},{inSec:15,outSec:20}]};
 const gaps=missingIntervals(s);
 assert(gaps.length===1&&gaps[0].startSec===8&&gaps[0].endSec===15,"overlap cannot hide missing coverage");
});
Deno.test("recovery does not authorize rendering or all-code film",()=>{
 const f=defaultFilm("Test","custom");
 f.scenes=[{id:"s",order:1,title:"Test",durationSec:10,narration:{text:"Une première idée très claire. Une seconde idée très précise."},shots:[]}];
 const g=productionGuidance(f,null,null,true)!;
 assert(g.kind==="fill_visual_gap"&&!g.fallback,"real verified media required before automatic code fallback");
 assert(!g.tools.includes("request_render"),"no premature rendering");
 assert(productionGuidance(f,{deltaSeconds:20},null,false)?.kind==="correct_duration","duration first");
 f.scenes[0].narration.text="";
 assert(productionGuidance(f,null,null,false)?.kind==="write_narration","narration first");
});
Deno.test("exact uncovered beat fallback preserves previous verified shot",()=>{
 const f=defaultFilm("Test","custom");
 f.media=[{id:"m",kind:"image",source:"search"}];
 f.scenes=[{id:"s",order:1,title:"Test",durationSec:10,narration:{text:"Une première idée très claire. Une seconde idée très précise."},shots:[{id:"a",order:1,inSec:0,outSec:5,mediaRef:"m",visualMode:"media",visualEvidence:{verifiedBy:"vision_observation_v1",actualVisualAnalysis:true,mediaRef:"m",narrationQuote:"Une première idée très claire.",visualIntent:"Image pertinente",hasContradiction:false,licenseChecked:true,samples:[{relevance:1,visualQuality:1,description:"Image",hasContradiction:false}]}}]}];
 const g=productionGuidance(f,null,null,true)!;
 assert(!!g.fallback&&g.fallback.inSec===5&&g.fallback.outSec===10,"exact missing beat");
 assert(!productionGuidance(f,null,null,false)?.fallback,"unmeasured voice cannot trigger fallback");
 const patched=applyOperation(f,"add_code_shot",g.fallback!).film;
 assert(patched.scenes[0].shots.length===2&&patched.scenes[0].shots[0].id==="a","existing media preserved");
 assert(missingIntervals(patched.scenes[0]).length===0,"coverage complete");
});

Deno.test("focus fills missing items without relaxing other diagram rules",()=>{
 const f=defaultFilm("Test","custom");
 const quote="Un mouvement décrit dans le récit.";
 f.scenes=[{id:"s",order:1,title:"Test",durationSec:5,narration:{text:quote},shots:[]}];
 const args={scene_id:"s",inSec:0,outSec:5,visualText:quote,visualType:"focus"};
 assert(repairFocus(f,"add_code_shot",args).args.visualItems[0]===quote,"missing focus item restored");
 assert(!repairFocus(f,"add_code_shot",{...args,visualType:"sphere_rotation"}).repair,"no invented 3D shape");
 assert(!repairFocus(f,"add_code_shot",{...args,visualType:"timeline"}).repair,"no invented timeline");
});
Deno.test("unverified documentary still requires factual review",()=>{
 const f=defaultFilm("Test","documentary");
 f.scenes=[{id:"s",order:1,title:"Test",durationSec:5,narration:{text:"La Terre tourne autour de son axe."},shots:[]}];
 const g=productionGuidance(f,null,null,true)!;
 assert(g.kind==="research"&&g.sceneId==="s"&&!g.fallback,"cannot bypass facts for fallback");
});

Deno.test("duplicate attachment must not erase existing evidence in autonomy",()=>{
 const f=defaultFilm("Test","custom");
 f.media=[{id:"m",kind:"image",provenance:{result_id:"wikimedia:123"}}];
 f.scenes=[{id:"s",shots:[{id:"a",mediaRef:"m",visualMode:"media",visualEvidence:{verifiedBy:"vision_observation_v1"}},{id:"b",visualMode:"programmatic"}]}];
 assert(redundantAttachment(f,"add_found_media",{shot_id:"a",result_id:"wikimedia:123"}),"same asset and shot");
 assert(redundantAttachment(f,"attach_media",{shot_id:"a",media_asset_id:"m"}),"same attachment");
 assert(!redundantAttachment(f,"add_found_media",{shot_id:"a",result_id:"wikimedia:456"}),"different asset remains allowed");
 assert(!redundantAttachment(f,"add_found_media",{shot_id:"b",result_id:"wikimedia:123"}),"different shot remains allowed");
 assert(!redundantAttachment(f,"verify_shot_media",{shot_id:"a"}),"verification remains allowed");
});

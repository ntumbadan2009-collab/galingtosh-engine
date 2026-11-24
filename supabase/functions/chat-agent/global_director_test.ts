import {auditGlobalContinuity} from "./global_director.ts";
const assert=(condition:unknown,msg:string)=>{if(!condition)throw Error(msg)};
const scene=(id:string,order:number,shot:string,mediaRef="photo")=>({id,order,durationSec:4,narration:{text:"Ce sont des informations différentes pour chaque scène "+id},shots:[{id:shot,order:0,inSec:0,outSec:4,mediaRef}]});
Deno.test("global ledger uses timeline order without changing the film",()=>{
 const f={scenes:[scene("b",2,"s2","other"),scene("a",1,"s1")],media:[{id:"photo",kind:"image"},{id:"other",kind:"image"}]};
 const original=JSON.stringify(f),r=auditGlobalContinuity(f);
 assert(r.plannedDurationSec===8&&r.sceneLedger[0].sceneId==="a"&&r.sceneLedger[1].startSec===4,"incorrect scene clock");
 assert(r.flagCount===0&&JSON.stringify(f)===original,"false positive or input mutation");
});
Deno.test("identifies a repeated planned image at a scene boundary without declaring it an artistic error",()=>{
 const f={scenes:[scene("a",1,"s1"),scene("b",2,"s2")],media:[{id:"photo",kind:"image"}]};
 const flag=auditGlobalContinuity(f).flags.find(x=>x.kind==="boundary_visual_repeat");
 assert(flag?.severity==="review"&&flag.startSec===4,"missing advisory at boundary");
 f.media[0].kind="video";
 assert(!auditGlobalContinuity(f).flags.some(x=>x.kind==="boundary_visual_repeat"),"a clip ID does not prove repeated frames");
});
Deno.test("detects gaps, duplicate IDs, orphan transitions and global timing errors",()=>{
 const a=scene("a",1,"s1"),b=scene("b",2,"s1");
 b.shots[0].inSec=1;
 const r=auditGlobalContinuity({scenes:[a,b],transitions:[{atShotId:"missing"}],subtitles:[{cues:[{startSec:7,endSec:9}]}],audio:{tracks:[{id:"voice",events:[{startSec:7,durationSec:2}]}]}});
 for(const kind of ["visual_gap","shot_id_invalid","orphan_transition","subtitle_out_of_range","audio_out_of_range"])assert(r.flags.some(x=>x.kind===kind),"missing "+kind);
 assert(r.flags.find(x=>x.kind==="visual_gap")?.startSec===4,"incorrect absolute position");
});
Deno.test("invalid clock never pretends to know later absolute positions",()=>{
 const a=scene("a",1,"s1"),b=scene("b",2,"s2");a.durationSec=NaN;
 const r=auditGlobalContinuity({scenes:[a,b]});
 assert(r.plannedDurationSec===null&&r.sceneLedger[1].startSec===null,"invented global time");
});
Deno.test("repeated narration is advisory and adjacent subtitle overlap is flagged",()=>{
 const a=scene("a",1,"s1"),b=scene("b",2,"s2");b.narration.text=a.narration.text;
 const r=auditGlobalContinuity({scenes:[a,b],subtitles:[{cues:[{startSec:1,endSec:3},{startSec:2,endSec:4}]}]});
 assert(r.flags.some(x=>x.kind==="adjacent_narration_repeat"&&x.severity==="review"),"missing repeat");
 assert(r.flags.some(x=>x.kind==="subtitle_overlap"),"missing subtitle overlap");
});
import {directorDiagnostics,makeDirectorBatches,parseDirectorReview,directorPassed,directorKey,directorReviewState} from "./director_intelligence.ts";
const assert=(v:unknown,m:string)=>{if(!v)throw Error(m)};
const throws=(fn:()=>unknown)=>{let ok=false;try{fn()}catch{ok=true}assert(ok,"expected refusal")};
const makeFilm=()=>({info:{type:"documentary"},scenes:[{id:"s",order:1,durationSec:5,title:"Test",narration:{text:"La Terre apparaît. Puis la nuit tombe."},shots:[{id:"a",order:1,inSec:0,outSec:2,visualMode:"programmatic",visualText:"La Terre apparaît."},{id:"b",order:2,inSec:2,outSec:5,visualMode:"programmatic",visualText:"Puis la nuit tombe."}]}],media:[],audio:{tracks:[]},transitions:[],effects:[],subtitles:[]});
const verdict=(b:any)=>({sceneId:b.sceneId,shotIds:b.shotIds,checks:{narrative:"pass",visual:"pass",rhythm:"pass",sound:"pass",continuity:"pass",audience:"pass"},observation:"La révélation brève précède la transition.",correction:"Aucune correction du plan.",shortExceptions:b.shortIds.map((shotId:string)=>({shotId,reason:"Révélation très brève avant le changement de sujet."}))});
Deno.test("director requires a reason for every short shot and exact review scope",()=>{
 const f=makeFilm(),b=makeDirectorBatches(f)[0],v=verdict(b);
 assert(directorDiagnostics(f).flags.some(x=>x.kind==="short_shot_needs_reason"&&x.shotId==="a"),"missing short flag");
 assert(directorPassed(parseDirectorReview(v,b)),"valid review rejected");
 throws(()=>parseDirectorReview({...v,shortExceptions:[]},b));
 throws(()=>parseDirectorReview({...v,shotIds:["b","a"]},b));
 throws(()=>parseDirectorReview({...v,shortExceptions:[{shotId:"b",reason:"Reason for wrong shot."}]},b));
 assert(!directorPassed(parseDirectorReview({...v,checks:{...v.checks,rhythm:"uncertain"}},b)),"uncertain passed");
});
Deno.test("revision-bound review is invalidated by any edit; reject malformed and incomplete evidence",async()=>{
 const f=makeFilm(),batches=makeDirectorBatches(f),b=batches[0],key=await directorKey(f,2,3);
 const requested={kind:"director_review_requested",status:"done",result:{key}};
 const review={kind:"director_plan_review",status:"done",result:{key,batch:0,verdict:verdict(b)}};
 assert(directorReviewState([],key,batches).status==="not_requested","missing request accepted");
 assert(directorReviewState([requested],key,batches).status==="pending","missing review accepted");
 assert(directorReviewState([requested,review],key,batches).status==="passed","valid review rejected");
 f.scenes[0].shots[0].outSec=2.1;
 const changed=await directorKey(f,2,3);assert(changed!==key,"content edit didn't invalidate");
 assert(directorReviewState([requested,review],changed,batches).status==="not_requested","stale review accepted");
 const bad={...review,result:{...review.result,verdict:{...verdict(b),checks:{...verdict(b).checks,sound:"revise"}}}};
 assert(directorReviewState([requested,bad],key,batches).status==="revise","failed review accepted");
 assert(directorReviewState([requested,{...review,result:{...review.result,verdict:{}}}],key,batches).status==="invalid","malformed evidence accepted");
});
Deno.test("every shot is included even in long scenes; neighbors and sound context preserved",()=>{
 const f=makeFilm();const s=f.scenes[0];
 s.shots=Array.from({length:41},(_,i)=>({id:"shot"+i,order:i+1,inSec:i*3,outSec:(i+1)*3,visualMode:"programmatic",visualText:"La Terre apparaît."}));
 s.durationSec=123;f.scenes.push({...s,id:"next",order:2,shots:[{...s.shots[0],id:"nextshot"}],durationSec:3});
 const batches=makeDirectorBatches(f);
 assert(batches.length===4&&batches.flatMap(x=>x.shotIds).length===42,"shot coverage incomplete");
 assert(batches[2].scene.next.sceneId==="next"&&batches[3].scene.previous.sceneId==="s","neighbor context missing");
});

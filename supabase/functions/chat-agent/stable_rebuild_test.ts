import {indexEvidence,materializeEvidence,researchIssues} from "./research.ts";
import {repairSceneLayout,sceneVisualReady,chooseCandidate,definitiveMediaChecks} from "./structured.ts";
import {applyOperation,defaultFilm} from "./film.ts";
const assert=(v:unknown)=>{if(!v)throw Error("assertion failed");};
const reject=(fn:()=>unknown)=>{let failed=false;try{fn()}catch{failed=true}assert(failed);};
const sources:any[]=[{id:"a",title:"Publication A",url:"https://example.org/a",organization:"A",workKey:"a",excerpt:"The observed result was confirmed in a controlled experiment.",kind:"publication"},{id:"b",title:"Publication B",url:"https://example.org/b",organization:"B",workKey:"b",excerpt:"The observed result was confirmed by a separate experiment.",kind:"publication"}];
Deno.test("research builds literal claims and real source quotations from IDs",()=>{
 const p=indexEvidence(sources);const r=materializeEvidence(sources,p,{reason:"Deux travaux",sentences:[{text:"Le résultat a été confirmé.",evidenceIds:[p[0].id,p.find(x=>x.sourceId==="b")!.id]}]});
 assert(r.review.claims[0].claim===r.narration);
 assert(r.review.claims[0].citations.every((c:any)=>sources.find(s=>s.id===c.sourceId).excerpt.includes(c.quote)));
 assert(!researchIssues({info:{type:"documentary",editorialLevel:5},scenes:[{id:"s",narration:{text:r.narration},researchEvidence:r.review}]}).length);
});
Deno.test("research rejects fabricated IDs and duplicate source references",()=>{
 const p=indexEvidence(sources);reject(()=>materializeEvidence(sources,p,{reason:"test",sentences:[{text:"Un fait narré.",evidenceIds:[p[0].id,"invented"]}]}));
 reject(()=>materializeEvidence(sources,p,{reason:"test",sentences:[{text:"Un fait narré.",evidenceIds:[p[0].id,p[0].id]}]}));
});
Deno.test("layout fixes overlaps and covers complete scene without restarting valid layout",()=>{
 let f=applyOperation(defaultFilm("Test"),"add_scene",{title:"Scene",narrativeGoal:"Test",durationSec:10}).film;
 const s=f.scenes[0];f=applyOperation(f,"set_scene_narration",{scene_id:s.id,text:"Une première idée est expliquée. Puis une seconde idée est présentée.",targetDurationSec:10}).film;
 f=applyOperation(f,"add_shot",{scene_id:s.id,inSec:0,outSec:3}).film;
 f=applyOperation(f,"add_shot",{scene_id:s.id,inSec:0,outSec:4}).film;
 const r=repairSceneLayout(f,s.id);assert(sceneVisualReady(r.film,r.film.scenes[0]));assert(!repairSceneLayout(r.film,s.id).changes.length);assert(r.film.scenes[0].shots.every((x:any)=>x.outSec-x.inSec<=5.001));
});
Deno.test("candidate selection cannot repeat rejected media",()=>{
 const x={result_id:"x",author:"A",license:"CC BY",url:"https://example.org/x",duration:10},y={...x,result_id:"y"};assert(chooseCandidate([x,y],new Set(["x"]),"video",4)?.result_id==="y");assert(!chooseCandidate([x],new Set(["x"]),"video",4));
});

Deno.test("provider outage is not a visual rejection",()=>{const rows=[{result:{candidateId:"a",transientProvider:true}},{result:{candidateId:"b",verified:false}}];const definitive=definitiveMediaChecks(rows);assert(definitive.length===1&&definitive[0].result.candidateId==="b");});

import {isMediaInputFailure,transientFailure} from "./structured.ts";
import {mediaInputFailure} from "./llm.ts";
Deno.test("unreachable media is not a quota outage even in historical mixed errors",()=>{
 const error="provider_rate_limited: HTTP 400 Cannot fetch content from the provided URL. HTTP 429";
 assert(isMediaInputFailure(error));
 assert(!transientFailure({kind:"structured_media_verify",result:{error,transientProvider:true}}));
 assert(transientFailure({kind:"structured_media_verify",result:{error:"provider_rate_limited: HTTP 429",transientProvider:true}}));
 assert(mediaInputFailure(400,"Cannot fetch content from the provided URL."));
 assert(!mediaInputFailure(429,"Cannot fetch content from the provided URL."));
 assert(definitiveMediaChecks([{result:{error,transientProvider:true}}]).length===1);
});

import {candidateScore,rejectedMediaIds,mediaAttemptLimit} from "./structured.ts";
Deno.test("named-entity candidate is prioritized over generic historic archive",()=>{
 const old={result_id:"old",title:"Breeder and sportsman (1891)",author:"A",license:"CC BY",url:"https://example.org/old"};
 const exact={...old,result_id:"exact",title:"OpenAI ChatGPT interface"};
 assert(chooseCandidate([old,exact],new Set(),"image",4,"OpenAI ChatGPT")?.result_id==="exact");
 assert(candidateScore(exact,"OpenAI ChatGPT")>candidateScore(old,"OpenAI ChatGPT"));
});
Deno.test("mission-wide definitive rejections are excluded; quotas are not",()=>{
 const rows=[{kind:"structured_media_verify",status:"failed",result:{candidateId:"bad",reason:"not relevant"}},{kind:"structured_media_verify",status:"failed",result:{candidateId:"quota",transientProvider:true,error:"HTTP 429"}}];
 const used=rejectedMediaIds(rows);assert(used.has("bad")&&!used.has("quota"));
 assert(mediaAttemptLimit(true)===1&&mediaAttemptLimit(false)===2);
});

import {auditFoundations,proceduralFallbackReady} from "./foundations.ts";
Deno.test("bounded procedural fallback preserves strict scene checks and rejects stale receipts",()=>{
 let f=applyOperation(defaultFilm("Test"),"add_scene",{title:"Scene",narrativeGoal:"Test",durationSec:4}).film;
 const id=f.scenes[0].id;f=applyOperation(f,"set_scene_narration",{scene_id:id,text:"Une idée précise est expliquée.",targetDurationSec:4}).film;
 f=applyOperation(f,"add_code_shot",{scene_id:id,inSec:0,outSec:4,visualText:"Une idée précise est expliquée."}).film;
 assert(!auditFoundations(f).passed);
 f.info.mediaFallback={version:1,reason:"licensed_media_exhausted",shotIds:[f.scenes[0].shots[0].id]};
 assert(proceduralFallbackReady(f));assert(auditFoundations(f).passed);
 f.info.mediaFallback.shotIds=["stale"];assert(!proceduralFallbackReady(f));assert(!auditFoundations(f).passed);
});

import {allowProviderRetry} from "./structured.ts";
Deno.test("optional visual quota outages cannot repeat forever",()=>{
 assert(allowProviderRetry("structured_media_verify",0));
 assert(!allowProviderRetry("structured_media_verify",1));
 assert(!allowProviderRetry("structured_media_recovery_plan",1));
 assert(allowProviderRetry("structured_voice_measure",3));
});

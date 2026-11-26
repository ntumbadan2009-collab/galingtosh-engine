import {indexEvidence,materializeEvidence,researchIssues} from "./research.ts";
import {repairSceneLayout,sceneVisualReady,chooseCandidate} from "./structured.ts";
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

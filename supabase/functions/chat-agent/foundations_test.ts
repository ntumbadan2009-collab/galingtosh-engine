import {auditFoundations} from "./foundations.ts";
const assert=(v:unknown,m:string)=>{if(!v)throw Error(m)};
function film(){
 const text="La Terre apparaît au-dessus de la Lune.";
 return {scenes:[{id:"s1",order:1,durationSec:4,narration:{text},shots:[{id:"p1",order:1,inSec:0,outSec:4,visualMode:"media",mediaRef:"m1",visualEvidence:{verifiedBy:"vision_observation_v1",actualVisualAnalysis:true,mediaRef:"m1",narrationQuote:text,visualIntent:"La Terre au-dessus de la Lune",hasContradiction:false,licenseChecked:true,samples:[{relevance:.95,visualQuality:.8,description:"Terre au-dessus de la Lune",hasContradiction:false}]}}]}],media:[{id:"m1",kind:"image",source:"search"}]};
}
Deno.test("allows verified real media with narration and continuous coverage",()=>{assert(auditFoundations(film()).passed,"valid film rejected")});
Deno.test("rejects all-code film, missing narration, orphan or unverified real media",()=>{
 const f=film();const sh=f.scenes[0].shots[0];
 for(const bad of [{...f,media:[]},{...f,scenes:[{...f.scenes[0],narration:{text:""},narrativeGoal:"Intention"}]},{...f,scenes:[{...f.scenes[0],shots:[{...sh,visualEvidence:null}]}]},{...f,scenes:[{...f.scenes[0],shots:[{...sh,visualMode:"programmatic",mediaRef:null}]}]}])assert(!auditFoundations(bad).passed,"invalid film accepted");
});
Deno.test("allows abstract code-only scene in hybrid film but refuses a timeline gap",()=>{
 const f=film();const abstract={id:"s2",order:2,durationSec:4,narration:{text:"Le phénomène s'explique par la gravité."},shots:[{id:"p2",order:1,inSec:0,outSec:4,visualMode:"programmatic",visualText:"Le phénomène s'explique par la gravité."}]};
 const hybrid={...f,scenes:[...f.scenes,abstract]};
 assert(auditFoundations(hybrid).passed,"artificial per-scene media quota");
 abstract.shots[0].inSec=1;assert(!auditFoundations(hybrid).passed,"timeline gap accepted");
});

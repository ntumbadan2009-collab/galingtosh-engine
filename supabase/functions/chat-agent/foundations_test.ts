import {auditFoundations,longShotSupported} from "./foundations.ts";
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

Deno.test("five seconds is the default; longer partial-scene shots require timing evidence",()=>{
 const f=film(),s=f.scenes[0],sh=s.shots[0],asset=f.media[0];
 s.durationSec=9;sh.outSec=9;
 assert(longShotSupported(s,sh,asset),"whole-scene image with exact full narration should be allowed");
 s.narration.text+=" Puis la capsule atterrit.";
 assert(!longShotSupported(s,sh,asset),"partial quote cannot justify long shot");
 sh.outSec=5;assert(longShotSupported(s,sh,asset),"five-second threshold");
 sh.outSec=5.01;assert(!longShotSupported(s,sh,asset),"threshold exceeded");
});
Deno.test("long video needs real evidence spanning the entire shot, not clustered frames",()=>{
 const f=film(),s=f.scenes[0],sh=s.shots[0],asset={...f.media[0],kind:"video"};
 s.durationSec=9;sh.outSec=9;
 const v={...sh,sourceInSec:10,visualEvidence:{...sh.visualEvidence,sourceInSec:10,samples:[11,14.5,18].map(atSec=>({...sh.visualEvidence.samples[0],atSec}))}};
 assert(longShotSupported({...s,shots:[v]},v,asset),"distributed actual samples rejected");
 v.visualEvidence.samples=[11,12,13].map(atSec=>({...sh.visualEvidence.samples[0],atSec}));
 assert(!longShotSupported({...s,shots:[v]},v,asset),"clustered samples accepted");
});
Deno.test("long code illustration must cover the entire narrated scene",()=>{
 const s={durationSec:8,narration:{text:"La gravité attire la matière."},shots:[{id:"code",inSec:0,outSec:8,visualMode:"programmatic",visualText:"La gravité attire la matière."}]};
 assert(longShotSupported(s,s.shots[0],null),"whole scene explanatory visual rejected");
 s.shots[0].visualText="La gravité";assert(!longShotSupported(s,s.shots[0],null),"incomplete quote accepted");
});

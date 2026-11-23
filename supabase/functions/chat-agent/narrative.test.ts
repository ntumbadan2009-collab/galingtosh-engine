import {defaultFilm,applyOperation} from "./film.ts";
import {narrativePreflight, planNarrativeBeats, quotedFromNarration, verifiedVisualEvidence} from "./narrative.ts";

function ok(value: unknown, message: string) {
  if(!value) throw new Error(message);
}
function throws(fn:()=>unknown, needle:string) {
  let error:Error|null=null;
  try {fn();}catch(e){error=e instanceof Error?e:new Error(String(e));}
  if(!error||!error.message.includes(needle))throw Error("Expected exception containing "+needle);
}
const narrative="L'intelligence artificielle analyse les documents. Mais ses conclusions ne sont pas toujours exactes.";
function seeded() {
  const f=defaultFilm("Recherche", "educational");
  f.scenes=[{id:"s1",title:"Comprendre",order:1,durationSec:12,narration:{text:narrative},shots:[]}];
  return f;
}
Deno.test("Beats contain only exact words of approved narration and preserve timeline",()=>{
  const beats=planNarrativeBeats(narrative,12);
  ok(beats.length>=2,"Need montage beats");
  ok(beats.every(b=>quotedFromNarration(seeded().scenes[0],b.quote)),"No invented quotes");
  ok(beats[0].startSec===0 && beats[beats.length-1].endSec===12,"Timeline must close");
  ok(beats.every((b,i)=>i===0||beats[i-1].endSec===b.startSec),"No timeline gaps");
});
Deno.test("A code shot is the safe first-class visual alternative to stock media",()=>{
  const original=seeded();
  const {film}=applyOperation(original,"add_code_shot",{
    scene_id:"s1",visualText:"L'intelligence artificielle analyse les documents.",
    inSec:0,outSec:6,cardStyle:"focus"
  });
  const next=applyOperation(film,"add_code_shot",{
    scene_id:"s1",visualText:"Mais ses conclusions ne sont pas toujours exactes.",
    inSec:6,outSec:12,cardStyle:"contrast"
  }).film;
  ok(narrativePreflight(next).length===0,"Code quote must pass without unrelated media");
  throws(()=>applyOperation(next,"add_code_shot",{scene_id:"s1",visualText:"99% de réussite",outSec:5}),
    "citer exactement");
});
Deno.test("Unreviewed stock media is blocked",()=>{
  const f=seeded();
  f.media=[{id:"m1",kind:"video",source:"search"}];
  f.scenes[0].shots=[{id:"p1",inSec:0,outSec:12,mediaRef:"m1"}];
  ok(narrativePreflight(f).some(i=>i.includes("non vérifiée")),"Need actual frame evidence");
});
Deno.test("Video evidence is invalid after changing source trim or narration",()=>{
  const f=seeded();
  f.media=[{id:"m1",kind:"video",source:"search"}];
  f.scenes[0].shots=[{id:"p1",inSec:0,outSec:12,mediaRef:"m1",sourceInSec:0}];
  const v:any={
    verifiedBy:"vision_observation_v1",actualVisualAnalysis:true,mediaRef:"m1",
    narrationQuote:"L'intelligence artificielle analyse les documents.",
    visualIntent:"Un ordinateur analyse réellement les documents",
    hasContradiction:false,licenseChecked:true,sourceInSec:0,
    samples:[1,4,8].map(atSec=>({atSec,description:"Documents affichés à l'écran",
      relevance:0.9,visualQuality:0.8,hasContradiction:false}))
  };
  const accepted=applyOperation(f,"record_visual_verification",{shot_id:"p1",evidence:v}).film;
  ok(narrativePreflight(accepted).length===0,"Three real frame reviews must pass");
  const changed=applyOperation(accepted,"update_shot",{shot_id:"p1",sourceInSec:3}).film;
  ok(narrativePreflight(changed).length>0,"Changing time must invalidate old evidence");
  ok(!verifiedVisualEvidence(accepted.scenes[0],changed.scenes[0].shots[0],f.media[0]),"No stale score");
});
Deno.test("Turn an unrelated shot into an exact code quote",()=>{
  const f=seeded();f.media=[{id:"m1",kind:"image",source:"search"}];
  f.scenes[0].shots=[{id:"p1",inSec:0,outSec:6,mediaRef:"m1"}];
  const converted=applyOperation(f,"turn_shot_into_code",{shot_id:"p1",
    visualText:"L'intelligence artificielle analyse les documents.",cardStyle:"focus"}).film;
  const shot=converted.scenes[0].shots[0];
  ok(!shot.mediaRef && shot.visualMode==="programmatic","Remove rejected asset");
  ok(narrativePreflight(converted).length===0,"Code plan should be usable");
});

import {defaultFilm} from "./film.ts";
import {previewPrecisionRevision,verifyPrecisionRevision} from "./precision_revision.ts";
const assert=(v:unknown,m:string)=>{if(!v)throw Error(m)};
const quote="L'eau chauffe puis elle devient vapeur.";
function fixture(){
 const f=defaultFilm("Test précision");
 f.scenes=[{id:"sc1",order:0,durationSec:6,narration:{text:quote},shots:[
 {id:"s1",order:0,inSec:0,outSec:3,visualMode:"programmatic",visualText:quote,camera:{type:"ken_burns"}},
 {id:"s2",order:1,inSec:3,outSec:6,visualMode:"programmatic",visualText:quote,camera:{type:"ken_burns"}}
 ]}];
 f.audio.tracks=[{id:"v",kind:"voiceover",events:[{startSec:0,durationSec:6}]}];
 f.subtitles=[{cues:[{startSec:0,endSec:6,text:quote}]}];
 return f;
}
const edit={shot_id:"s1",visualType:"steps",visualItems:["L'eau chauffe","elle devient vapeur"]};
async function refuses(fn:()=>Promise<unknown>){let denied=false;try{await fn()}catch{denied=true}assert(denied,"must refuse")}
Deno.test("changes only the explicitly scoped diagram; entire remaining film stays identical",async()=>{
 const f=fixture(),original=JSON.stringify(f),p=await previewPrecisionRevision(f,[edit]);
 assert(JSON.stringify(f)===original,"source mutated");
 assert(p.candidate.scenes[0].shots[0].visualSpec.type==="steps","missing revision");
 const restored=structuredClone(p.candidate);delete restored.scenes[0].shots[0].visualSpec;
 assert(JSON.stringify(restored)===original,"out-of-scope change");
 assert(p.receipt.applied===false&&p.receipt.sourceHash!==p.receipt.candidateHash,"invalid receipt");
 await verifyPrecisionRevision(f,[edit],p.receipt.sourceHash,p.receipt.candidateHash);
});
Deno.test("rejects duplicate, unknown, ungrounded, unscoped and no-op edits",async()=>{
 const f=fixture();
 for(const e of [[edit,edit],[{...edit,shot_id:"absent"}],[{...edit,visualItems:["invented fact"]}],[{...edit,inSec:1}],[]])
  await refuses(()=>previewPrecisionRevision(f,e));
 const p=await previewPrecisionRevision(f,[edit]);await refuses(()=>previewPrecisionRevision(p.candidate,[edit]));
});
Deno.test("rejects stale film and swapped candidate",async()=>{
 const f=fixture(),p=await previewPrecisionRevision(f,[edit]);
 f.scenes[0].narration.text+=" Autre phrase.";
 await refuses(()=>verifyPrecisionRevision(f,[edit],p.receipt.sourceHash,p.receipt.candidateHash));
 await refuses(()=>verifyPrecisionRevision(f,[edit],p.receipt.sourceHash,"0".repeat(64)));
});
Deno.test("batch is all or nothing and does not replace real media",async()=>{
 const f=fixture(),original=JSON.stringify(f);
 await refuses(()=>previewPrecisionRevision(f,[edit,{...edit,shot_id:"s2",visualItems:["not in narration"]}]));
 assert(JSON.stringify(f)===original,"partial batch persisted");
 f.scenes[0].shots[0].visualMode="media";
 await refuses(()=>previewPrecisionRevision(f,[edit]));
});
Deno.test("ambiguous duplicate target cannot be revised",async()=>{
 const f=fixture();f.scenes[0].shots[1].id="s1";
 await refuses(()=>previewPrecisionRevision(f,[edit]));
});
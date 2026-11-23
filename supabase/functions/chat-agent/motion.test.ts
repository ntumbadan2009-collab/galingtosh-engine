import {defaultFilm, applyOperation} from "./film.ts";
import {motionSpecIssues, narrativePreflight} from "./narrative.ts";

const assert=(v:unknown,msg:string)=>{if(!v)throw Error(msg);};
const fails=(f:()=>unknown,needle:string)=>{
  let error="";
  try{f();}catch(e){error=String(e);}
  if(!error.includes(needle))throw Error("Expected refusal: "+needle+"; actual: "+error);
};
function setup(text:string){
  const f=defaultFilm("Level 2","educational");
  f.scenes=[{id:"scene1",title:"Comprendre",order:1,durationSec:9,
    narration:{text},shots:[]}];
  return f;
}
Deno.test("Animated steps have exact ordered narrative citations",()=>{
  const quote="Le moteur collecte les données, puis les classe et ensuite les vérifie.";
  const f=setup(quote);
  const out=applyOperation(f,"add_code_shot",{
    scene_id:"scene1",visualText:quote,inSec:0,outSec:9,
    visualType:"steps",visualItems:[
      "Le moteur collecte les données","puis les classe","ensuite les vérifie"
    ]});
  assert(out.film.scenes[0].shots[0].visualSpec.type==="steps","No animated plan");
  assert(narrativePreflight(out.film).length===0,"Safe narrative animation refused");
});
Deno.test("Cannot invent a node or reverse narrative order",()=>{
  const quote="La machine classe les lettres, puis elle trie les dossiers.";
  const f=setup(quote);
  fails(()=>applyOperation(f,"add_code_shot",{scene_id:"scene1",visualText:quote,outSec:8,
    visualType:"steps",visualItems:["10 millions de lettres", "elle trie les dossiers"]}),"citation");
  fails(()=>applyOperation(f,"add_code_shot",{scene_id:"scene1",visualText:quote,outSec:8,
    visualType:"steps",visualItems:["elle trie les dossiers","La machine classe les lettres"]}),"ordre");
});
Deno.test("Comparison only with explicit contrast, timeline only temporal order",()=>{
  const quote="Cette méthode est rapide, mais l'autre méthode est lente.";
  const f=setup(quote);
  const v=applyOperation(f,"add_code_shot",{scene_id:"scene1",visualText:quote,outSec:9,
    visualType:"comparison",visualItems:["Cette méthode est rapide","mais l'autre méthode est lente"]});
  assert(narrativePreflight(v.film).length===0,"Explicit comparison should work");
  fails(()=>applyOperation(f,"add_code_shot",{scene_id:"scene1",visualText:quote,outSec:9,
    visualType:"timeline",visualItems:["Cette méthode est rapide","mais l'autre méthode est lente"]}),"temporelle");
});
Deno.test("A procedural shot can be upgraded without replacing other shots",()=>{
  const q="La première étape rassemble les textes, ensuite nous les expliquons.";
  const f=setup(q);
  let x=applyOperation(f,"add_code_shot",{scene_id:"scene1",visualText:q,outSec:9}).film;
  const id=x.scenes[0].shots[0].id;
  x=applyOperation(x,"set_motion_visual",{shot_id:id,visualType:"steps",
     visualItems:["La première étape rassemble les textes","ensuite nous les expliquons"]}).film;
  assert(x.scenes[0].shots[0].visualSpec?.items.length===2,"Animation not saved");
  assert(narrativePreflight(x).length===0,"Upgraded shot fails preflight");
});
Deno.test("Switching back to a real media asset discards stale code diagram",()=>{
  const quote="Le projet présente une étude, puis un nouveau rapport.";
  let x=applyOperation(setup(quote),"add_code_shot",{scene_id:"scene1",visualText:quote,
    outSec:9,visualType:"steps",
    visualItems:["Le projet présente une étude","puis un nouveau rapport"]}).film;
  x.media.push({id:"m1",kind:"image",source:"upload"});
  const id=x.scenes[0].shots[0].id;
  x=applyOperation(x,"update_shot",{shot_id:id,mediaRef:"m1"}).film;
  assert(x.scenes[0].shots[0].visualSpec===undefined,"Stale programmatic spec leaked");
  assert(narrativePreflight(x).length>0,"Real media must be reviewed");
});

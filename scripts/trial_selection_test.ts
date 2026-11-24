import {applyTrialSelection,parseVariantReview,selectVariant} from "../supabase/functions/chat-agent/variant_review.ts";
const encoder=new TextEncoder();
async function digest(bytes:Uint8Array){
 return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new Uint8Array(bytes)))).map(x=>x.toString(16).padStart(2,"0")).join("");
}
const p={relevance:"pass",readability:"pass",composition:"pass",observation:"Fixture test, not a model verdict."};
async function fixture(dir:string){
 const hashes:Record<string,string>={};
 for(const id of ["A","B"]){const bytes=encoder.encode("test payload "+id);hashes[id]=await digest(bytes);await Deno.writeFile(dir+"/"+id+".mp4",bytes);}
 const planHashes:Record<string,string>={};
 for(const id of ["A","B"]){const data=encoder.encode(JSON.stringify({id,fixture:true}));planHashes[id]=await digest(data);await Deno.writeFile(dir+"/"+id+".film.json",data);}
 const pair=encoder.encode(JSON.stringify({shots:[{shotId:"s1"}]}));
 await Deno.writeFile(dir+"/paired_000.json",pair);
 const manifest=encoder.encode(JSON.stringify({version:1,status:"needs_artistic_review",candidates:["A","B"].map(id=>({id,sha256:hashes[id],filmSha256:planHashes[id],audioSha256:null,report:{editorial_quality:{passed:true}}})),pairedEvidence:[{index:0,file:"paired_000.json",count:1,sha256:await digest(pair)}]}));
 await Deno.writeFile(dir+"/comparison.json",manifest);
 const rows=parseVariantReview(JSON.stringify([{shotId:"s1",A:p,B:p,preference:"B",reason:"Fixture preference."}]),["s1"]);
 return {...selectVariant(rows),manifestSha256:await digest(manifest),candidateHashes:hashes,rows,usage:{input:1,output:1},limitations:"Fixture only"};
}
async function rejects(fn:()=>Promise<unknown>){
 let rejected=false;try{await fn()}catch{rejected=true}if(!rejected)throw Error("Expected rejection");
}
Deno.test("private selection copies exact winner; leaves originals unchanged",async()=>{
 const dir=await Deno.makeTempDir();
 try{
  const review=await fixture(dir);
  const r=await applyTrialSelection(dir,review);
  if(r.status!=="private_selection"||r.winner!=="B"||!("version" in r))throw Error("No versioned selection");
  const selected=dir+"/selected-"+r.version;
  if(await digest(await Deno.readFile(selected+"/selected.mp4"))!==review.candidateHashes.B)throw Error("Wrong output");
  const receipt=JSON.parse(await Deno.readTextFile(selected+"/selection.json"));
  if(receipt.publication!==false||receipt.winner!=="B"||receipt.scope!=="scene_snapshot")throw Error("Unsafe receipt");
  if(await digest(await Deno.readFile(selected+"/selected.film.json"))!==await digest(await Deno.readFile(dir+"/B.film.json")))throw Error("Wrong scene plan");
  if(await digest(await Deno.readFile(dir+"/A.mp4"))!==review.candidateHashes.A)throw Error("Original changed");
  await rejects(()=>applyTrialSelection(dir,review));
 }finally{await Deno.remove(dir,{recursive:true});}
});
Deno.test("changed candidate, evidence or manifest cannot commit",async()=>{
 for(const name of ["A.mp4","B.mp4","A.film.json","B.film.json","paired_000.json","comparison.json"]){
  const dir=await Deno.makeTempDir();
  try{
   const review=await fixture(dir);
   await Deno.writeTextFile(dir+"/"+name,"tampered");
   await rejects(()=>applyTrialSelection(dir,review));
   for await(const entry of Deno.readDir(dir)){if(entry.name.startsWith("selected-"))throw Error("Invalid selection persisted");}
  }finally{await Deno.remove(dir,{recursive:true});}
 }
});

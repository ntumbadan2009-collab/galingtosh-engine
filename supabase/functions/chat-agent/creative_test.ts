import {CREATIVE_ROLES,nextRole,parseCreative} from "./creative.ts";
Deno.test("independent creative phases and strict decision validation",()=>{
 const rows:any[]=[];
 for(const role of CREATIVE_ROLES){
  if(nextRole(rows)!==role)throw Error("incorrect role sequence");
  rows.push({kind:role,status:"done"});
 }
 if(nextRole(rows)!==undefined)throw Error("loop");
 const good=parseCreative("creative_director",{selected:"visual",reason:"Concrete demonstration",brief:"Show relevant verified media"});
 if(!("selected" in good)||good.selected!=="visual")throw Error("decision lost");
 let invalid=false;try{parseCreative("creative_director",{selected:"invented",reason:"x",brief:"x"})}catch{invalid=true}
 if(!invalid)throw Error("unrecognized candidate accepted");
 invalid=false;try{parseCreative("creative_narrative",{concept:"hook"})}catch{invalid=true}
 if(!invalid)throw Error("incomplete proposal accepted");
});

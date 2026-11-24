import {validateResearch,researchIssues} from "./research.ts";
Deno.test("actual source quotations, two sources and stale narration",()=>{
 const narration="Le phénomène a été observé.";
 const sources:any[]=[
 {id:"a",title:"Source A",url:"https://example.org/a",organization:"A",workKey:"a",excerpt:"The phenomenon was observed in controlled conditions.",kind:"publication"},
 {id:"b",title:"Source B",url:"https://example.org/b",organization:"B",workKey:"b",excerpt:"The phenomenon was observed in the experiment.",kind:"publication"}];
 const raw={noFactualClaims:false,reason:"Affirmation examinée.",claims:[{claim:narration,status:"supported",citations:[{sourceId:"a",quote:"The phenomenon was observed"},{sourceId:"b",quote:"The phenomenon was observed"}]}]};
 const review=validateResearch(narration,sources,raw);
 const film={info:{editorialLevel:5,type:"documentary"},scenes:[{id:"s",narration:{text:narration},researchEvidence:review}]};
 if(researchIssues(film).length)throw Error("valid review refused");
 film.scenes[0].narration.text="Autre affirmation.";
 if(!researchIssues(film).length)throw Error("stale review accepted");
 raw.claims[0].citations[1].quote="Invented quotation";
 let refused=false;try{validateResearch(narration,sources,raw)}catch{refused=true}
 if(!refused)throw Error("invented quotation accepted");
});

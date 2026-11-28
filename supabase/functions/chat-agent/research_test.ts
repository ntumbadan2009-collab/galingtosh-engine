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

import {indexEvidence,materializeEvidence,selectEvidence,rankSources} from "./research.ts";
Deno.test("compact passage catalogue and harmless ID formatting keep exact evidence",()=>{
 const sources:any[]=[
 {id:"a",title:"AI technical report",url:"https://example.org/a",organization:"A",workKey:"a",excerpt:"The system was released. ".repeat(180),kind:"publication"},
 {id:"b",title:"AI review",url:"https://example.org/b",organization:"B",workKey:"b",excerpt:"The system was released. ".repeat(180),kind:"encyclopedia"}];
 const ordered=rankSources(sources,"AI system released"),p=selectEvidence(ordered,"system released");
 if(p.length>12||p.length<2)throw Error("passage budget");
 const first=p.find(x=>x.sourceId==="a")!,second=p.find(x=>x.sourceId==="b")!;
 const raw={reason:"Two sources",sentences:[{text:"Le système a été publié.",evidenceIds:[" "+first.id.toUpperCase()+" ",second.id]}]};
 const result=materializeEvidence(ordered,p,raw);
 if(result.review.claims[0].citations.length!==2)throw Error("missing citations");
 raw.sentences[0].evidenceIds=[first.id,"p999_0"];
 let rejected=false;try{materializeEvidence(ordered,p,raw)}catch{rejected=true}
 if(!rejected)throw Error("invented ID accepted");
});
Deno.test("two publications from the same organization are not independent evidence",()=>{
 const sources:any[]=[
 {id:"a",title:"A",url:"https://example.org/a",organization:"Same",workKey:"a",excerpt:"The system was released in the experiment.",kind:"publication"},
 {id:"b",title:"B",url:"https://example.org/b",organization:"Same",workKey:"b",excerpt:"The system was released in the experiment.",kind:"publication"}];
 const p=indexEvidence(sources);
 let rejected=false;try{materializeEvidence(sources,p,{reason:"Test",sentences:[{text:"Le système a été publié.",evidenceIds:[p[0].id,p[1].id]}]})}catch{rejected=true}
 if(!rejected)throw Error("same organization accepted");
});

import {dataCiteSources} from "./research.ts";
Deno.test("DataCite accepts real abstracts and canonicalizes related preprints",()=>{
 const attributes={doi:"10.48550/arxiv.2303.08774",types:{resourceTypeGeneral:"Preprint"},titles:[{title:"Technical report"}],publisher:"arXiv",descriptions:[{descriptionType:"Abstract",description:"The system was evaluated on multiple tests. ".repeat(5)}],relatedIdentifiers:[{relatedIdentifierType:"DOI",relationType:"IsPreprintOf",relatedIdentifier:"10.1000/published"}]};
 const sources=dataCiteSources({data:[{attributes},{attributes:{...attributes,doi:"10.1000/noabstract",descriptions:[]}},{attributes:{...attributes,doi:"10.1000/dataset",types:{resourceTypeGeneral:"Dataset"}}}]});
 if(sources.length!==1||sources[0].workKey!=="10.1000/published"||!sources[0].title.startsWith("Prépublication"))throw Error("DataCite validation failed");
});

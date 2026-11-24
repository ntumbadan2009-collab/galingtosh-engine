import {candidateRepairs} from "./cinematic_repair.ts";
Deno.test("repair is localized, preserves source and refuses uncertainty",()=>{
 const quote="Une démonstration claire.";
 const snapshot={info:{editorialLevel:5,visualPolicy:"strict"},scenes:[{id:"s",durationSec:4,narration:{text:quote},shots:[
 {id:"a",order:1,inSec:0,outSec:2,visualMode:"programmatic",visualText:quote,visualSpec:{type:"focus",items:[{text:quote}]}},
 {id:"b",order:2,inSec:2,outSec:4,visualMode:"programmatic",visualText:quote}]}]};
 const original=JSON.stringify(snapshot);
 const evidence={verdict:[{shotId:"a",relevance:"pass",readability:"fail",composition:"pass"}]};
 const result=candidateRepairs(snapshot,[{passed:false,evidence}]);
 if(!result||result.ids.join()!=="a"||result.film.scenes[0].shots[0].visualSpec!==undefined)throw Error("repair missing");
 if(JSON.stringify(snapshot)!==original||JSON.stringify(result.film.scenes[0].shots[1])!==JSON.stringify(snapshot.scenes[0].shots[1]))throw Error("unrelated change");
 evidence.verdict[0].readability="uncertain";
 if(candidateRepairs(snapshot,[{passed:false,evidence}]))throw Error("uncertainty is not a safe repair");
});

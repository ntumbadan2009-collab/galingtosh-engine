import {parseReview,reviewPassed,validateManifest} from "./cinematic.ts";
Deno.test("requires exact shot coverage and treats uncertainty as rejection",()=>{
 const ids=["a","b"];
 const verdict=(shotId:string)=>({shotId,observation:"Image examinée.",relevance:"pass",readability:"pass",composition:"pass"});
 const good=[verdict("a"),verdict("b")];
 if(!reviewPassed(parseReview(JSON.stringify(good),ids)))throw Error("valid rejected");
 for(const bad of [[verdict("a")],[verdict("a"),verdict("a")],[verdict("a"),verdict("other")]]){
  let refused=false;try{parseReview(JSON.stringify(bad),ids)}catch{refused=true}
  if(!refused)throw Error("incomplete coverage accepted");
 }
 good[1].relevance="uncertain";
 if(reviewPassed(parseReview(JSON.stringify(good),ids)))throw Error("uncertain passed");
 if(validateManifest({version:1,sampling:"two_final_frames_per_shot",batches:[{index:2,count:1}]}))throw Error("invalid index accepted");
});

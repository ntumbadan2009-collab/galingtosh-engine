// Final delivery review: explicit technical conditions, never simulated human judgment.
export function finalDeliveryReview(report:any,expectedSeconds:number,strict:boolean){
 const reasons:string[]=[];
 const actual=report?.duration_seconds;
 if(typeof actual!=="number"||!Number.isFinite(actual)||actual<=0||!Number.isFinite(expectedSeconds)||expectedSeconds<=0||Math.abs(actual-expectedSeconds)>Math.max(2,expectedSeconds*.05))reasons.push("duration");
 if(!Number.isInteger(report?.width)||report.width<=0||!Number.isInteger(report?.height)||report.height<=0)reasons.push("dimensions");
 if(strict&&report?.editorial_quality?.passed!==true)reasons.push("editorial_technical_check");
 const audio=report?.final_audio_review;
 const soundReview=report?.audio===true?(audio?.status==="measured"&&Array.isArray(audio.review_flags)?audio.review_flags.length?"review_recommended":"measured":"unavailable"):"no_audio";
 return {version:1,technicalPassed:reasons.length===0,reasons,soundReview,
  semanticAudioReview:"not_performed",continuousMotionReview:"not_performed",humanReview:"not_performed"};
}

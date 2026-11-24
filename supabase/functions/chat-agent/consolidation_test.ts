import {defaultFilm,applyOperation} from "./film.ts";
import {projectPreferences,validatePreferences} from "./preferences.ts";
import {finalDeliveryReview} from "./delivery_review.ts";
const assert=(v:unknown,m:string)=>{if(!v)throw Error(m)};
Deno.test("creative preferences require consent and can be removed without changing other settings",()=>{
 const f=defaultFilm("Test"); const preferences={pace:"dynamic",visuals:"documentary",sound:"minimal"};
 assert(projectPreferences(f).active===false,"default must not profile");
 let failed=false;try{applyOperation(f,"set_creative_preferences",{preferences})}catch{failed=true}assert(failed,"no consent");
 const next=applyOperation(f,"set_creative_preferences",{enabled:true,preferences}).film;
 assert(projectPreferences(next).active&&projectPreferences(next).pace==="dynamic","preference missing");
 assert(projectPreferences({...next,info:{...next.info,creativePreferencesConsent:false}}).active===false,"consent ignored");
 const clear=applyOperation(next,"set_creative_preferences",{enabled:false}).film;
 assert(JSON.stringify(clear)===JSON.stringify(f),"revocation changes unrelated data");
 failed=false;try{validatePreferences({...preferences,tracking:"yes"})}catch{failed=true}assert(failed,"unknown field accepted");
});
Deno.test("delivery gate fails missing strict QA and distinguishes audio measurement from semantic review",()=>{
 const report={duration_seconds:150,width:1280,height:720,audio:true,editorial_quality:{passed:true},final_audio_review:{status:"measured",review_flags:[]}};
 const d=finalDeliveryReview(report,150,true);
 assert(d.technicalPassed&&d.soundReview==="measured"&&d.semanticAudioReview==="not_performed","claim too strong");
 for(const bad of [{...report,duration_seconds:130},{...report,width:0},{...report,editorial_quality:null}])assert(!finalDeliveryReview(bad,150,true).technicalPassed,"accepted invalid report");
 assert(finalDeliveryReview({...report,final_audio_review:null},150,true).soundReview==="unavailable","invented evidence");
});

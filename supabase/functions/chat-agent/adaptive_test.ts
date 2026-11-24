import {auditRhythm,editorialStrategy} from "./adaptive.ts";
import {defaultFilm,applyOperation} from "./film.ts";
Deno.test("repetition is advisory, no media quotas, explicit profile wins",()=>{
 const f=defaultFilm("test","educational");
 f.scenes=[{id:"s",durationSec:24,shots:[0,1,2,3].map(i=>({id:String(i),order:i,inSec:i*6,outSec:(i+1)*6,visualMode:"programmatic",visualText:"Exact text"}))}];
 const r=auditRhythm(f);
 if(r.visualSeconds.textCard!==24||r.flags[0]?.kind!=="repetition_to_review"||r.strategy.style!=="educational")throw Error("missing evidence");
 const updated=applyOperation(f,"set_editorial_profile",{style:"youtube"}).film;
 if(editorialStrategy(updated).style!=="youtube"||f.info.editorialProfile!==undefined)throw Error("profile mutation");
 let refused=false;try{applyOperation(f,"set_editorial_profile",{style:"unknown"})}catch{refused=true}
 if(!refused)throw Error("invalid profile");
});

import {durationMatches,preflight} from "./production.ts";
function assert(value:boolean,message:string){if(!value)throw Error(message);}
Deno.test("duration matches only actual numeric duration",()=>{
 assert(durationMatches(600,600),"10 minute duration");
 assert(!durationMatches(150,600),"short output must not pass");
 assert(!durationMatches("600",600),"invalid metadata");
});
Deno.test("preflight refuses blank scenes and missing media",()=>{
 assert(preflight({scenes:[]},600)!==null,"empty movie");
 assert(preflight({scenes:[{durationSec:600,shots:[]}]},600)!==null,"missing shots");
 assert(preflight({scenes:[{durationSec:600,shots:[{mediaRef:"a"}]}],media:[]},600)!==null,"missing media");
 assert(preflight({scenes:[{durationSec:600,shots:[{mediaRef:"a"}]}],media:[{id:"a"}]},600)!==null,
   "A file attached by ID is not automatically semantically relevant");
 assert(preflight({scenes:[{durationSec:6,narration:{text:"Une démonstration illustrée fidèlement."},
   shots:[{inSec:0,outSec:6,visualMode:"programmatic",visualText:"Une démonstration illustrée fidèlement."}]}]},6)===null,
   "A code illustration quoting the approved narration is a complete plan");
});

import {parseSoundVerdict} from "./sound.ts";
Deno.test("sound verdict must contain explicit observed content and all verdict fields",()=>{
 const good=parseSoundVerdict(JSON.stringify({match:"pass",containsSpeech:false,containsMusic:false,observation:"Deux impulsions sonores."}));
 if(good.match!=="pass")throw Error("valid result refused");
 for(const bad of [{match:"pass",observation:"tags"}, {match:"pass",containsSpeech:"false",containsMusic:false,observation:"x"}]){
  let refused=false;try{parseSoundVerdict(JSON.stringify(bad))}catch{refused=true}
  if(!refused)throw Error("malformed evidence accepted");
 }
});

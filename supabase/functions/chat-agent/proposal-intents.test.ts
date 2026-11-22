import {interpretPlanReply} from "./proposal-intents.ts";
function equals(actual:unknown,expected:unknown,reason:string){if(actual!==expected)throw new Error(reason+" => "+String(actual));}
Deno.test("approval replies include OK and natural French variants",()=>{
 for(const example of ["ok","OK !","okay","Oui","Je valide","Je confirme le plan","Vas-y !","D'accord.","Lance la production.","C'est bon !","Tu peux commencer","On y va"]){
  equals(interpretPlanReply(example),"approve",example);
 }
});
Deno.test("refusal replies are recognized",()=>{
 for(const example of ["non","Je refuse","Annule le plan","Ne lance pas."])
  equals(interpretPlanReply(example),"reject",example);
});
Deno.test("compound instructions and unrelated texts never silently approve",()=>{
 for(const example of ["ok mais je préfère 90 secondes","Oui, mais change le scénario","Je ne valide pas encore","Est-ce que c'est bon ?","Merci","ok, après modification","Je valide la scène 2","lance pas la production"])
  equals(interpretPlanReply(example),null,example);
});

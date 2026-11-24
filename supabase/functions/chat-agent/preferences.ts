// Explicit per-project preferences, never inferred from behavior or used as
// authority to change the approved brief, factual evidence or media licenses.
const options={
 pace:["auto","calm","balanced","dynamic"],
 visuals:["auto","documentary","explanatory","cinematic"],
 sound:["auto","minimal","balanced","expressive"]
} as const;
type Key=keyof typeof options;
type Preferences=Record<Key,string>;
const defaults:Preferences={pace:"auto",visuals:"auto",sound:"auto"};
export function validatePreferences(raw:unknown):Preferences{
 if(!raw||typeof raw!=="object"||Array.isArray(raw))throw Error("Préférences invalides.");
 const r=raw as Record<string,unknown>;
 if(Object.keys(r).sort().join(",")!=="pace,sound,visuals")throw Error("Préférences incomplètes ou non prises en charge.");
 for(const k of Object.keys(options) as Key[])if(typeof r[k]!=="string"||!(options[k] as readonly string[]).includes(r[k] as string))throw Error("Préférence inconnue : "+k);
 return {pace:r.pace as string,visuals:r.visuals as string,sound:r.sound as string};
}
export function projectPreferences(film:any){
 try{
  const p=validatePreferences(film?.info?.creativePreferences);
  if(film?.info?.creativePreferencesConsent!==true)return {...defaults,active:false};
  return {...p,active:true};
 }catch{return {...defaults,active:false};}
}
export const PREFERENCE_POLICY="Les préférences projet explicitement approuvées sont des conseils seulement. Aucun apprentissage implicite ou transfert entre utilisateurs. La demande actuelle, les preuves, les licences et le silence demandé priment. auto signifie aucun biais de style.";

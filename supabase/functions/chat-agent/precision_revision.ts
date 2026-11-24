// Level 8 first slice: isolated, revision-bound edits to existing code diagrams.
// No media fetch, new factual content, timeline changes or rendering.
import {applyOperation,type Json} from "./film.ts";
import {MOTION_TYPES} from "./narrative.ts";
type Edit={shot_id:string;visualType:string;visualItems:string[]};
const list=(x:any):any[]=>Array.isArray(x)?x:[];
function canonical(x:any):string{
 if(x===null||typeof x!=="object")return JSON.stringify(x)??"undefined";
 if(Array.isArray(x))return "["+x.map(canonical).join(",")+"]";
 return "{"+Object.keys(x).sort().map(k=>JSON.stringify(k)+":"+canonical(x[k])).join(",")+"}";
}
async function digest(x:any):Promise<string>{
 const bytes=new TextEncoder().encode(canonical(x));
 return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(v=>v.toString(16).padStart(2,"0")).join("");
}
function locate(film:Json,id:string){
 const hits=list(film.scenes).flatMap(sc=>list(sc.shots).filter(sh=>sh.id===id).map(sh=>({sc,sh})));
 if(hits.length!==1)throw Error("Plan absent ou identifiant ambigu.");
 return hits[0];
}
function parseEdits(raw:unknown):Edit[]{
 if(!Array.isArray(raw)||!raw.length||raw.length>4)throw Error("Une révision contient 1 à 4 plans.");
 const ids=new Set<string>();
 return raw.map(e=>{
  if(!e||typeof e!=="object"||Object.keys(e).sort().join(",")!=="shot_id,visualItems,visualType"||
    typeof e.shot_id!=="string"||!e.shot_id.trim()||e.shot_id.length>128||ids.has(e.shot_id)||
    !(MOTION_TYPES as readonly string[]).includes(e.visualType)||!Array.isArray(e.visualItems)||
    e.visualItems.length<1||e.visualItems.length>4||e.visualItems.some((s:any)=>typeof s!=="string"||s.length<5||s.length>125))
   throw Error("Révision invalide ou plan dupliqué.");
  ids.add(e.shot_id);
  return {shot_id:e.shot_id,visualType:e.visualType,visualItems:[...e.visualItems]};
 });
}
function outsideSpecs(film:Json,ids:Set<string>){
 const f=structuredClone(film);
 for(const sc of list(f.scenes))for(const sh of list(sc.shots))if(ids.has(sh.id))delete sh.visualSpec;
 return canonical(f);
}
export async function previewPrecisionRevision(source:Json,raw:unknown){
 const edits=parseEdits(raw);
 const ids=new Set(edits.map(e=>e.shot_id));
 let candidate=structuredClone(source);
 const changes=[];
 for(const edit of edits){
  const {sc,sh}=locate(candidate,edit.shot_id);
  if(sh.visualMode!=="programmatic"||sh.mediaRef||typeof sh.visualText!=="string"||!sh.visualText.trim())
   throw Error("Première tranche : seuls les schémas programmatiques existants peuvent être révisés.");
  const before=structuredClone(sh.visualSpec??null);
  candidate=applyOperation(candidate,"set_motion_visual",edit).film;
  const after=structuredClone(locate(candidate,edit.shot_id).sh.visualSpec??null);
  if(canonical(before)===canonical(after))throw Error("La révision ne change pas le plan.");
  changes.push({sceneId:sc.id,shotId:sh.id,inSec:sh.inSec,outSec:sh.outSec,before,after});
 }
 if(outsideSpecs(source,ids)!==outsideSpecs(candidate,ids))
  throw Error("Révision refusée : modification hors du périmètre autorisé.");
 const sourceHash=await digest(source),candidateHash=await digest(candidate);
 return {candidate,receipt:{scope:"visualSpec_only",sourceHash,candidateHash,edits,changes,applied:false,
  limitations:"Contrôle structurel uniquement; le MP4, le son réel et la qualité artistique n'ont pas été vérifiés."}};
}
export async function verifyPrecisionRevision(source:Json,raw:unknown,sourceHash:string,candidateHash:string){
 const p=await previewPrecisionRevision(source,raw);
 if(p.receipt.sourceHash!==sourceHash||p.receipt.candidateHash!==candidateHash)
  throw Error("Le film ou la proposition a changé : recrée une prévisualisation.");
 return p;
}

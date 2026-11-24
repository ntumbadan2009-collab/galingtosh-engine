// Level 7 prototype: a global edit ledger, not a semantic or audience score.
// Pure read-only analysis of the current Film JSON. No edits or media requests.
type Flag={kind:string;severity:"check"|"review";sceneIds?:string[];shotIds?:string[];trackId?:string;startSec?:number;detail:string};
const list=(v:unknown):any[]=>Array.isArray(v)?v:[];
const number=(v:unknown):v is number=>typeof v==="number"&&Number.isFinite(v);
const text=(v:unknown)=>typeof v==="string"?v.trim():"";
const normalized=(v:unknown)=>text(v).normalize("NFC").toLocaleLowerCase().replace(/[\p{P}\p{Z}\s]+/gu," ").trim();
const round=(v:number)=>Math.round(v*1000)/1000;
const ordered=(v:unknown)=>[...list(v)].sort((a,b)=>(number(a?.order)?a.order:Infinity)-(number(b?.order)?b.order:Infinity));
export function auditGlobalContinuity(film:any){
 const flags:Flag[]=[];
 let count=0;
 const add=(flag:Flag)=>{count++;if(flags.length<80)flags.push(flag);};
 const scenes=ordered(film?.scenes);
 const media=new Map(list(film?.media).map(m=>[m?.id,m]));
 const seenScenes=new Set<string>(),seenShots=new Set<string>(),seenOrders=new Set<number>();
 let duration=0,validClock=true;
 const ledger:{sceneId:string;title:string;startSec:number|null;endSec:number|null;narrationExcerpt:string;firstShotId:string|null;lastShotId:string|null}[]=[];
 let previous:{sceneId:string;last:any;narration:string}|null=null;
 const signature=(shot:any):string=>{
  if(!shot)return "";
  if(shot.visualMode==="programmatic"){
   const q=normalized(shot.visualText);
   return q?JSON.stringify(["code",q,shot.visualSpec??null,shot.cardStyle??null]):"";
  }
  const m=media.get(shot.mediaRef);
  if(m?.kind==="image")return JSON.stringify(["image",shot.mediaRef,shot.camera??null]);
  return ""; // Reusing a clip ID does not prove repeated footage.
 };
 for(const sc of scenes){
  const id=text(sc?.id);
  if(!id||seenScenes.has(id))add({kind:"scene_id_invalid",severity:"check",sceneIds:[id],detail:"Identifiant de scène manquant ou dupliqué."});
  seenScenes.add(id);
  if(!number(sc?.order)||seenOrders.has(sc.order))add({kind:"scene_order_invalid",severity:"check",sceneIds:[id],detail:"Ordre de scène absent ou ambigu."});
  else seenOrders.add(sc.order);
  const d=sc?.durationSec;
  const start=validClock?round(duration):null;
  const shots=ordered(sc?.shots);
  const narration=normalized(sc?.narration?.text);
  if(!number(d)||d<=0){validClock=false;add({kind:"scene_duration_invalid",severity:"check",sceneIds:[id],detail:"Durée invalide; horloge globale non fiable."});}
  let cursor=0;
  for(const sh of shots){
   const sid=text(sh?.id);
   if(!sid||seenShots.has(sid))add({kind:"shot_id_invalid",severity:"check",sceneIds:[id],shotIds:[sid],detail:"Identifiant de plan manquant ou dupliqué."});
   seenShots.add(sid);
   const a=sh?.inSec,b=sh?.outSec;
   if(!number(a)||!number(b)||a<0||b<=a||!number(d)||b>d+.08){
    add({kind:"shot_range_invalid",severity:"check",sceneIds:[id],shotIds:[sid],detail:"Intervalle du plan invalide."});continue;
   }
   if(Math.abs(a-cursor)>.08)add({kind:a>cursor?"visual_gap":"visual_overlap",severity:"check",sceneIds:[id],shotIds:[sid],...(start!==null?{startSec:round(start+Math.min(a,cursor))}:{}),detail:"Rupture de couverture visuelle sur la timeline."});
   cursor=Math.max(cursor,b);
  }
  if(number(d)&&d>0&&Math.abs(cursor-d)>.08)add({kind:"scene_tail_uncovered",severity:"check",sceneIds:[id],detail:"Fin de scène sans couverture visuelle complète."});
  if(previous){
   if(narration.length>=40&&narration===previous.narration)add({kind:"adjacent_narration_repeat",severity:"review",sceneIds:[previous.sceneId,id],detail:"Narrations successives identiques; vérifier si la répétition est volontaire."});
   const first=shots[0],sig=signature(first);
   if(sig&&sig===signature(previous.last))add({kind:"boundary_visual_repeat",severity:"review",sceneIds:[previous.sceneId,id],shotIds:[text(previous.last?.id),text(first?.id)],...(start!==null?{startSec:start}:{}),detail:"Même composition prévue de part et d'autre de la coupe; un rappel intentionnel est permis."});
  }
  if(validClock&&number(d))duration+=d;
  ledger.push({sceneId:id,title:text(sc?.title).slice(0,120),startSec:start,endSec:validClock?round(duration):null,narrationExcerpt:text(sc?.narration?.text??sc?.narrativeGoal).slice(0,220),firstShotId:shots.length?text(shots[0]?.id):null,lastShotId:shots.length?text(shots.at(-1)?.id):null});
  previous={sceneId:id,last:shots.at(-1),narration};
 }
 if(!scenes.length)add({kind:"empty_film",severity:"check",detail:"Film sans scènes."});
 for(const t of list(film?.transitions))if(!seenShots.has(text(t?.atShotId)))add({kind:"orphan_transition",severity:"check",shotIds:[text(t?.atShotId)],detail:"Transition rattachée à un plan absent."});
 if(validClock){
  for(const track of list(film?.subtitles)){
   const cues=[...list(track?.cues)].sort((a,b)=>(number(a?.startSec)?a.startSec:Infinity)-(number(b?.startSec)?b.startSec:Infinity));
   let end=0;
   for(const cue of cues){
    const a=cue?.startSec,b=cue?.endSec;
    if(!number(a)||!number(b)||a<0||b<=a||b>duration+.08){add({kind:"subtitle_out_of_range",severity:"check",trackId:text(track?.id),detail:"Sous-titre hors du film ou intervalle invalide."});continue;}
    if(a<end-.08)add({kind:"subtitle_overlap",severity:"review",trackId:text(track?.id),startSec:round(a),detail:"Sous-titres simultanés sur la même piste; vérifier la lisibilité."});
    end=Math.max(end,b);
   }
  }
  for(const track of list(film?.audio?.tracks))for(const event of list(track?.events)){
   const a=event?.startSec,d=event?.durationSec;
   if(!number(a)||!number(d)||a<0||d<=0||a+d>duration+.08)add({kind:"audio_out_of_range",severity:"check",trackId:text(track?.id),detail:"Événement audio hors de la timeline du film."});
  }
 }
 return {version:1,plannedDurationSec:validClock?round(duration):null,sceneCount:scenes.length,sceneLedger:ledger.slice(0,60),ledgerTruncated:ledger.length>60,flagCount:count,flags,flagsTruncated:count>flags.length,limitations:"Analyse du plan de montage seulement. Aucun jugement de pertinence, d'émotion, de qualité audio ou de rétention. Les répétitions sont des questions, pas des erreurs artistiques. Aucun changement automatique."};
}

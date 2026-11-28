import {verifiedVisualEvidence} from "./narrative.ts";
import {auditGlobalContinuity} from "./global_director.ts";
export const FOUNDATION_POLICY = `FONDATIONS OBLIGATOIRES DE TOUTE PRODUCTION COMPLÈTE : narration réellement écrite dans chaque scène, médias photo/vidéo réels et pertinents lorsqu'ils sont disponibles, continuité de la narration et du langage visuel, synchronisation et contrôle final. Une intention de scène ne remplace pas la voix off. Cherche des médias concrets pour les passages observables, même lorsque le code serait plus facile. Un média hors sujet est interdit : cherche un autre angle ou une autre source, puis utilise un schéma fidèle si le passage est abstrait. Ne transforme pas systématiquement le film en cartes. Pas de quota artificiel par scène. Après épuisement de la recherche bornée, des illustrations procédurales fidèles et variées peuvent constituer un film complet; signale explicitement ce secours. Aucun média hors sujet ne doit être ajouté pour satisfaire un quota. Ne génère aucune image ou vidéo par IA. Pour chaque scène, examine objectif narratif, émotion, médias candidats, cadrage, rythme, transitions, effets, animation, voix, musique, sons, silence, texte et lisibilité; choisis seulement les techniques compatibles et utiles. Une coupe simple ou le silence peuvent être le meilleur choix. Maintiens une direction visuelle cohérente et des raccords motivés. Les limites du catalogue sont réelles : ne promets jamais d'effet non pris en charge. Les diagnostics structurels ne prouvent pas la cohérence artistique ni l'écoute du résultat. Respecte les demandes sans musique ou sans effets; elles ne suppriment pas les fondations. Les productions partielles et les essais techniques ne sont pas des films complets. RYTHME OBLIGATOIRE : 3 à 5 secondes par plan par défaut. Un plan de moins de 3 secondes doit répondre à une nécessité de montage justifiée lors de la revue de direction; jamais pour accélérer arbitrairement. Dès que la narration change d'idée, d'objet ou d'action, change réellement le visuel au moment correspondant. Un plan plus long est permis seulement s'il continue à illustrer toute la narration de son intervalle, du début à la fin, avec preuve suffisante. Ne fractionne jamais artificiellement une image identique pour contourner la règle; ne garde pas un plan hors sujet même 1 seconde. Sans minutage fiable des mots, la seule exception actuellement vérifiable est un plan couvrant toute une scène dont la citation visuelle reprend toute la narration. Pour une vidéo longue, vérifie les images échantillonnées sur toute la plage; aucune preuve de mouvement continu n'est prétendue.`;
const arr=(x:any):any[]=>Array.isArray(x)?x:[];
const norm=(x:unknown)=>typeof x==="string"?x.normalize("NFC").replace(/\s+/gu," ").trim().toLocaleLowerCase("fr"):"";
export function longShotSupported(scene:any,shot:any,asset:any):boolean{
 const start=Number(shot?.inSec),end=Number(shot?.outSec),duration=end-start;
 if(!Number.isFinite(duration)||duration<=0)return false;
 if(duration<=5.000001)return true;
 // Without word-level timecodes, a partial scene cannot prove which
 // narration is spoken throughout a long shot. Do not infer from word count.
 if(!Number.isFinite(Number(scene?.durationSec))||Math.abs(start)>.001||
    Math.abs(end-Number(scene.durationSec))>.001||arr(scene?.shots).length!==1)return false;
 const spoken=norm(scene?.narration?.text);
 if(!spoken)return false;
 if(shot.visualMode==="programmatic")return !shot.mediaRef&&norm(shot.visualText)===spoken&&duration<=12;
 if(!verifiedVisualEvidence(scene,shot,asset)||norm(shot.visualEvidence.narrationQuote)!==spoken||duration>16)return false;
 if(asset?.kind==="image")return true;
 if(asset?.kind!=="video")return false;
 const origin=Number(shot.sourceInSec??0);
 const times=arr(shot.visualEvidence.samples).map(v=>Number(v.atSec)-origin).sort((a,b)=>a-b);
 return times.length>=3&&times.every(Number.isFinite)&&times[0]<=duration*.25&&
   times.at(-1)!>=duration*.75&&times.some(t=>t>=duration*.25&&t<=duration*.75);
}
// Only the orchestrator records exhaustion, after its bounded search pass.
// Existing films without this receipt still require verified real footage.
export function proceduralFallbackReady(film:any):boolean{
 const receipt=film?.info?.mediaFallback,shots=arr(film?.scenes).flatMap(s=>arr(s.shots));
 const ids=shots.map(sh=>sh.id).sort();
 return receipt?.version===1&&receipt.reason==="licensed_media_exhausted"&&
  Array.isArray(receipt.shotIds)&&JSON.stringify([...receipt.shotIds].sort())===JSON.stringify(ids)&&
  ids.length>0&&new Set(ids).size===ids.length&&shots.every(sh=>sh.visualMode==="programmatic"&&!sh.mediaRef);
}
export function auditFoundations(film:any){
 const scenes=arr(film?.scenes), media=new Map(arr(film?.media).map(m=>[m.id,m]));
 const issues:string[]=[]; let real=0,code=0,unverified=0;
 const sceneChoices=[];
 if(!scenes.length)issues.push("Aucune scène.");
 for(const [i,s] of scenes.entries()){
  if(typeof s?.narration?.text!=="string"||!s.narration.text.trim())issues.push("Scène "+(i+1)+" : narration écrite obligatoire.");
  let sceneReal=0,sceneCode=0;
  for(const sh of arr(s?.shots)){
   if(!longShotSupported(s,sh,media.get(sh.mediaRef)))issues.push("Scène "+(i+1)+", plan "+String(sh.id??"?")+" : maximum 5 s sans preuve couvrant toute la narration du passage. Recompose le plan et ses visuels, sans simple duplication.");
   if(sh.visualMode==="programmatic"){code++;sceneCode++;continue;}
   if(verifiedVisualEvidence(s,sh,media.get(sh.mediaRef))){real++;sceneReal++;}
   else unverified++;
  }
  sceneChoices.push({sceneId:s.id,verifiedRealShots:sceneReal,codeShots:sceneCode,review:sceneReal===0?"Examiner les possibilités de médias réels pertinents; un schéma seul peut être justifié pour une scène abstraite.":"Vérifier la cohérence avec les scènes voisines."});
 }
 if(unverified)issues.push("Des plans réels ne disposent pas encore de preuve visuelle valide.");
 if(!real&&!proceduralFallbackReady(film))issues.push("Rechercher un média réel pertinent ou enregistrer l’épuisement de la recherche bornée avant le secours procédural.");
 const continuity=auditGlobalContinuity(film);
 if(continuity.flags.some(f=>f.severity==="check")||continuity.flagsTruncated)issues.push("Corriger les incohérences structurelles de la timeline signalées par le réalisateur global.");
 return {passed:issues.length===0,issues,proceduralFallback:!real&&proceduralFallbackReady(film),verifiedRealShots:real,codeShots:code,unverifiedShots:unverified,sceneChoices:sceneChoices.slice(0,60),continuityFlags:continuity.flags,limitations:"Contrôle du plan; aucune mesure de cohérence esthétique ni écoute sémantique."};
}

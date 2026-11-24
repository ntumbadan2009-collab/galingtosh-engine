import {verifiedVisualEvidence} from "./narrative.ts";
import {auditGlobalContinuity} from "./global_director.ts";
export const FOUNDATION_POLICY = `FONDATIONS OBLIGATOIRES DE TOUTE PRODUCTION COMPLÈTE : narration réellement écrite dans chaque scène, médias photo/vidéo réels et pertinents dans le film, continuité de la narration et du langage visuel, synchronisation et contrôle final. Une intention de scène ne remplace pas la voix off. Cherche des médias concrets pour les passages observables, même lorsque le code serait plus facile. Un média hors sujet est interdit : cherche un autre angle ou une autre source, puis utilise un schéma fidèle si le passage est abstrait. Ne transforme jamais tout le film en cartes. Pas de quota artificiel par scène, ni d'obligation d'utiliser à la fois des photos et des vidéos. Si aucun média réel pertinent ne peut être vérifié, ne livre pas une production complète; signale le blocage. Ne génère aucune image ou vidéo par IA. Pour chaque scène, examine objectif narratif, émotion, médias candidats, cadrage, rythme, transitions, effets, animation, voix, musique, sons, silence, texte et lisibilité; choisis seulement les techniques compatibles et utiles. Une coupe simple ou le silence peuvent être le meilleur choix. Maintiens une direction visuelle cohérente et des raccords motivés. Les limites du catalogue sont réelles : ne promets jamais d'effet non pris en charge. Les diagnostics structurels ne prouvent pas la cohérence artistique ni l'écoute du résultat. Respecte les demandes sans musique ou sans effets; elles ne suppriment pas les fondations. Les productions partielles et les essais techniques ne sont pas des films complets.`;
const arr=(x:any):any[]=>Array.isArray(x)?x:[];
export function auditFoundations(film:any){
 const scenes=arr(film?.scenes), media=new Map(arr(film?.media).map(m=>[m.id,m]));
 const issues:string[]=[]; let real=0,code=0,unverified=0;
 const sceneChoices=[];
 if(!scenes.length)issues.push("Aucune scène.");
 for(const [i,s] of scenes.entries()){
  if(typeof s?.narration?.text!=="string"||!s.narration.text.trim())issues.push("Scène "+(i+1)+" : narration écrite obligatoire.");
  let sceneReal=0,sceneCode=0;
  for(const sh of arr(s?.shots)){
   if(sh.visualMode==="programmatic"){code++;sceneCode++;continue;}
   if(verifiedVisualEvidence(s,sh,media.get(sh.mediaRef))){real++;sceneReal++;}
   else unverified++;
  }
  sceneChoices.push({sceneId:s.id,verifiedRealShots:sceneReal,codeShots:sceneCode,review:sceneReal===0?"Examiner les possibilités de médias réels pertinents; un schéma seul peut être justifié pour une scène abstraite.":"Vérifier la cohérence avec les scènes voisines."});
 }
 if(unverified)issues.push("Des plans réels ne disposent pas encore de preuve visuelle valide.");
 if(!real)issues.push("Production complète : au moins un plan photo ou vidéo réel, effectivement attaché et vérifié, est indispensable. Recherche un média pertinent; aucun quota par scène.");
 const continuity=auditGlobalContinuity(film);
 if(continuity.flags.some(f=>f.severity==="check")||continuity.flagsTruncated)issues.push("Corriger les incohérences structurelles de la timeline signalées par le réalisateur global.");
 return {passed:issues.length===0,issues,verifiedRealShots:real,codeShots:code,unverifiedShots:unverified,sceneChoices:sceneChoices.slice(0,60),continuityFlags:continuity.flags,limitations:"Contrôle du plan; aucune mesure de cohérence esthétique ni écoute sémantique."};
}

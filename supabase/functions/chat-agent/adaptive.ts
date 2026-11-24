// Advisory, observable editorial diagnostics. Never quotas or engagement predictions.
export const STYLES=["auto","documentary","educational","youtube","social","cinematic","commercial"] as const;
export function editorialStrategy(film:any){
 const explicit=film?.info?.editorialProfile;
 const genre=film?.info?.type;
 const inferred=genre==="documentary"||genre==="reportage"?"documentary":genre==="educational"?"educational":genre==="social"?"social":genre==="ad"?"commercial":genre==="fiction"||genre==="short_film"?"cinematic":"auto";
 const style=STYLES.includes(explicit)&&explicit!=="auto"?explicit:inferred;
 const priorities:Record<string,string>={
 auto:"Décider selon le récit et le public, pas un format imposé.",
 documentary:"Privilégier les preuves visuelles réelles vérifiées; schémas pour expliquer ce que l'archive ne montre pas.",
 educational:"Clarté et progression; démonstrations réelles si utiles, schémas pour les mécanismes abstraits.",
 youtube:"Accroche honnête, progression, variété motivée, respirations; ne pas imiter un créateur.",
 social:"Entrée directe, lisibilité mobile, montage concis sans sacrifier les informations essentielles.",
 cinematic:"Continuité spatiale et émotionnelle, composition, pauses et transitions motivées.",
 commercial:"Démonstration concrète et bénéfices étayés; aucune promesse inventée."
 };
 return {style,priority:priorities[style],rule:"Aucun quota de médias réels ou procéduraux. Un média réel hors sujet est refusé. Une carte répétitive n'est pas une solution artistique par défaut."};
}
export function auditRhythm(film:any){
 let offset=0;let last="",runStart=0,runDuration=0,runIds:string[]=[];
 const spans:any[]=[]; const flags:any[]=[]; const totals:Record<string,number>={realImage:0,realVideo:0,unverifiedMedia:0,diagram:0,textCard:0};
 const media=new Map((film?.media??[]).map((m:any)=>[m.id,m]));
 function flush(){
  if(runDuration>=18&&runIds.length>=3)flags.push({kind:"repetition_to_review",visualKind:last,startSec:runStart,durationSec:runDuration,shotIds:runIds});
  runDuration=0;runIds=[];
 }
 for(const sc of [...(film?.scenes??[])].sort((a,b)=>(a.order??0)-(b.order??0))){
  const duration=Number(sc.durationSec);
  if(!Number.isFinite(duration)||duration<=0)continue;
  for(const sh of [...(sc.shots??[])].sort((a,b)=>(a.order??0)-(b.order??0))){
   const a=Number(sh.inSec),b=Number(sh.outSec);
   if(!Number.isFinite(a+b)||a<0||b<=a||b>duration+.08)continue;
   const m:any=media.get(sh.mediaRef);
   const verified=sh.visualEvidence?.verifiedBy==="vision_observation_v1"&&sh.visualEvidence?.actualVisualAnalysis===true&&sh.visualEvidence?.mediaRef===sh.mediaRef;
   const kind=sh.visualMode==="programmatic"?(sh.visualSpec&&sh.visualSpec.type!=="focus"?"diagram":"textCard"):verified&&m?.kind==="video"?"realVideo":verified&&m?.kind==="image"?"realImage":"unverifiedMedia";
   const key=kind==="diagram"?"diagram:"+sh.visualSpec.type:kind;
   const length=b-a;
   totals[kind]+=length;
   if(key!==last){flush();last=key;runStart=offset+a;}
   runDuration+=length;runIds.push(String(sh.id));
   spans.push({shotId:sh.id,sceneId:sc.id,startSec:offset+a,durationSec:length,visualKind:kind});
   if(kind==="unverifiedMedia")flags.push({kind:"verify_or_replace",shotId:sh.id});
  }
  offset+=duration;
 }
 flush();
 return {strategy:editorialStrategy(film),plannedDurationSec:offset,visualSeconds:Object.fromEntries(Object.entries(totals).map(([k,v])=>[k,Math.round(v*100)/100])),shotCount:spans.length,flags:flags.slice(0,40),limitations:"Mesures du plan de montage, pas observation du MP4 ni prédiction de rétention. Une répétition peut être justifiée; ne pas remplacer par un média moins pertinent."};
}

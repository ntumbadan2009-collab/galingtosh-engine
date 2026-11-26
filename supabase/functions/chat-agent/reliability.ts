import {applyOperation, type Json} from "./film.ts";
import {motionSpecIssues, quotedFromNarration, verifiedVisualEvidence, planNarrativeBeats} from "./narrative.ts";
import {researchIssues} from "./research.ts";

const arr=(v:any):any[]=>Array.isArray(v)?v:[];
const EPS=.002;
type Guidance={kind:string;sceneId?:string;shotId?:string;tools:string[];details?:unknown;fallback?:Json};

// Prefer exact current film state over the model's recollection. No mutation here.
export function missingIntervals(scene:any){
 const end=Number(scene.durationSec);
 if(!Number.isFinite(end)||end<=0)return [];
 const spans=arr(scene.shots).map(s=>[Number(s.inSec),Number(s.outSec)]).filter(([a,b])=>Number.isFinite(a)&&Number.isFinite(b)&&a>=0&&b>a).sort((a,b)=>a[0]-b[0]);
 const gaps:{startSec:number;endSec:number}[]=[];
 let cursor=0;
 for(const [a,b] of spans){
  if(a>cursor+EPS&&cursor<end)gaps.push({startSec:cursor,endSec:Math.min(a,end)});
  cursor=Math.max(cursor,b);
 }
 if(cursor<end-EPS)gaps.push({startSec:cursor,endSec:end});
 return gaps;
}

// Narrow only the recovery turn, not the ordinary creative toolbox.
export function productionGuidance(film:any,durationFeedback:any,voiceFeedback:any,voiceAligned:boolean):Guidance|null{
 const scenes=arr(film?.scenes),assets=new Map(arr(film?.media).map(m=>[m.id,m]));
 if(!scenes.length)return {kind:"create_scene",tools:["add_scene"],details:"Créer une première scène conforme au plan approuvé."};
 const unwritten=scenes.find(s=>typeof s.narration?.text!=="string"||!s.narration.text.trim());
 if(unwritten)return {kind:"write_narration",sceneId:unwritten.id,tools:["set_scene_narration"],details:{durationSec:unwritten.durationSec}};
 if(durationFeedback||voiceFeedback)return {kind:"correct_duration",tools:["set_scene_narration","update_scene","add_scene"],details:durationFeedback??voiceFeedback};
 const research=researchIssues(film);
 if(research.length){
  const scene=scenes.find(s=>research.some(i=>i.startsWith("Scène "+s.id+" :")));
  return {kind:"research",sceneId:scene?.id,tools:["review_documentary_scene","set_scene_narration"],details:research.slice(0,3)};
 }
 const real=scenes.some(s=>arr(s.shots).some(sh=>verifiedVisualEvidence(s,sh,assets.get(sh.mediaRef))));
 const pending=scenes.flatMap(s=>arr(s.shots).filter(sh=>sh.visualMode!=="programmatic"&&!verifiedVisualEvidence(s,sh,assets.get(sh.mediaRef))).map(sh=>({s,sh})))[0];
 if(pending)return {kind:"verify_visual",sceneId:pending.s.id,shotId:pending.sh.id,tools:["verify_shot_media","search_media","add_found_media","turn_shot_into_code","update_shot"],details:{inSec:pending.sh.inSec,outSec:pending.sh.outSec}};
 for(const s of scenes){
  const gaps=missingIntervals(s);
  if(!gaps.length)continue;
  const gap=gaps[0];
  const beats=planNarrativeBeats(s.narration.text,Number(s.durationSec));
  const candidates=beats.filter(b=>b.startSec>=gap.startSec-EPS&&b.endSec<=gap.endSec+EPS);
  const g:Guidance={kind:"fill_visual_gap",sceneId:s.id,tools:["add_code_shot","add_shot","search_media","add_found_media","inspect_video_clips","verify_shot_media"],details:{gap,beats:candidates.length?candidates:beats.filter(b=>b.startSec<gap.endSec&&b.endSec>gap.startSec)}};
  // Last resort only: an exact estimated beat, an already verified real
  // medium elsewhere, completed research and measured voice. Never overwrite
  // existing plans; never bypass the independent director or final preflight.
  const b=candidates.find(b=>Math.abs(b.startSec-gap.startSec)<=EPS);
  const shots=arr(s.shots);
  const sorted=shots.every((sh,i)=>i===0||Number(sh.inSec)>=Number(shots[i-1].outSec)-EPS);
  if(voiceAligned&&real&&sorted&&b&&b.quote.length<=125&&b.endSec-b.startSec>=3-EPS&&b.endSec-b.startSec<=5+EPS&&quotedFromNarration(s,b.quote)){
   const inSec=gap.startSec,outSec=Math.min(gap.endSec,b.endSec),position=shots.filter(sh=>Number(sh.outSec)<=inSec+EPS).length+1;
   if(outSec-inSec>=3-EPS&&outSec-inSec<=5+EPS&&!shots.some(sh=>Number(sh.inSec)<outSec-EPS&&Number(sh.outSec)>inSec+EPS)){
    const args={scene_id:s.id,inSec,outSec,position,visualText:b.quote,visualType:"focus",visualItems:[b.quote],cardStyle:b.presentation==="question"?"question":"focus"};
    try{applyOperation(film,"add_code_shot",args);g.fallback=args;}catch{/* ambiguous: require a creative decision instead */}
   }
  }
  return g;
 }
 return null;
}

// Repair only focus cardinality when the full, literal citation fits the
// exact validator. Leave other diagrams, durations, media and facts untouched.
export function repairFocus(film:Json,name:string,args:Json):{args:Json;repair?:string}{
 if(!["add_code_shot","turn_shot_into_code","set_motion_visual"].includes(name)||args.visualType!=="focus")return {args};
 const scenes=arr(film.scenes);
 const scene=name==="add_code_shot"?scenes.find(s=>s.id===args.scene_id):scenes.find(s=>arr(s.shots).some(sh=>sh.id===args.shot_id));
 if(!scene)return {args};
 const shot=arr(scene.shots).find(sh=>sh.id===args.shot_id);
 if(name==="set_motion_visual"&&shot?.visualMode!=="programmatic")return {args};
 const quote=name==="set_motion_visual"?shot?.visualText:args.visualText;
 if(typeof quote!=="string"||quote.length>125||!quotedFromNarration(scene,quote))return {args};
 const spec={type:"focus",items:Array.isArray(args.visualItems)?args.visualItems.map((text:unknown)=>({text})):[]};
 if(!motionSpecIssues(scene,{visualText:quote,visualSpec:spec}).length)return {args};
 const corrected={...args,visualItems:[quote]};
 // Dry-run the existing operation including every strict validation.
 try{applyOperation(film,name,corrected);}catch{return {args};}
 return {args:corrected,repair:"focus : citation exacte regroupée en un seul élément"};
}

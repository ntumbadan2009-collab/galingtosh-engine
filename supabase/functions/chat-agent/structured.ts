import {applyOperation,type Json} from "./film.ts";
import {complete,type ToolDef} from "./llm.ts";
import {execTool,type Ctx} from "./tools.ts";
import {directorKey} from "./director_intelligence.ts";
import {researchIssues,researchedNarration} from "./research.ts";
import {planNarrativeBeats,quotedFromNarration,verifiedVisualEvidence,motionSpecIssues} from "./narrative.ts";
import {auditFoundations,longShotSupported} from "./foundations.ts";
import {editorialTimelineIssues} from "./editorial.ts";

type Row={id:string;data:Json;version:number;rev:number};
type Mission={id:string;user_id:string;project_id:string;conversation_id:string;goal:string;plan:string;target_seconds:number;step_count:number;max_steps:number};
const arr=(x:any):any[]=>Array.isArray(x)?x:[];
const near=(a:number,b:number,t=.015)=>Math.abs(a-b)<=t;
const ordered=(v:any)=>[...arr(v)].sort((a,b)=>Number(a.order)-Number(b.order));
const S={type:"string"}, N={type:"number"};
const kinds=["structured_script","structured_research_query","structured_research","structured_voice_measure","structured_voice_rate","structured_voice_align","structured_visual_layout","structured_visual_plan","structured_media_search","structured_media_attach","structured_media_verify","structured_media_fallback","structured_subtitles","structured_project_type","structured_director_revision"];
type Ledger={kind:string;status:string;result:any;step_no:number};
export function exactQuote(scene:any,start:number,end:number){
 const text=String(scene.narration?.text??"").trim(), duration=Number(scene.durationSec);
 if(!text||!Number.isFinite(duration)||duration<=0)throw Error("missing_narration");
 const beats=planNarrativeBeats(text,duration);
 const best=[...beats].sort((a,b)=>Math.max(0,Math.min(b.endSec,end)-Math.max(b.startSec,start))-Math.max(0,Math.min(a.endSec,end)-Math.max(a.startSec,start)))[0];
 let q=best?.quote??text;
 if(q.length>280){const n=q.lastIndexOf(" ",280);q=q.slice(0,n>5?n:280);}
 if(!quotedFromNarration(scene,q))throw Error("literal_quote_missing");
 return q;
}
function focusArgs(scene:any,start:number,end:number){
 const q=exactQuote(scene,start,end);
 const n=q.length<=125?q.length:q.lastIndexOf(" ",125);
 const fragment=q.slice(0,n>4?n:125);
 return {visualText:q,visualType:"focus",visualItems:[fragment],cardStyle:q.includes("?")?"question":"focus"};
}
function assetMap(film:any){return new Map(arr(film.media).map(x=>[x.id,x]));}
function validShot(scene:any,sh:any,assets:Map<any,any>){
 const a=Number(sh.inSec),b=Number(sh.outSec),d=Number(scene.durationSec);
 if(![a,b,d].every(Number.isFinite)||a<0||b>a+d||b<=a||b>d+.001||b-a<Math.min(1,d)-.001||!longShotSupported(scene,sh,assets.get(sh.mediaRef)))return false;
 if(sh.visualMode==="programmatic")return !sh.mediaRef&&quotedFromNarration(scene,sh.visualText)&&!motionSpecIssues(scene,sh).length;
 return verifiedVisualEvidence(scene,sh,assets.get(sh.mediaRef));
}
export function sceneVisualReady(film:any,scene:any){
 const assets=assetMap(film),shots=ordered(scene.shots);
 return !!shots.length&&shots.every(sh=>validShot(scene,sh,assets))&&!editorialTimelineIssues({...film,scenes:[scene]}).length;
}
/** Repair a broken scene, not the whole movie. Keep verified real shots, and
 * preserve code plans whose exact slot and quote still match. */
export function repairSceneLayout(src:Json,sceneId:string){
 const scene=arr(src.scenes).find(s=>s.id===sceneId);
 if(!scene)throw Error("scene_missing");
 if(sceneVisualReady(src,scene))return {film:src,changes:[] as any[]};
 const assets=assetMap(src),duration=Number(scene.durationSec),old=arr(scene.shots);
 const keep=old.filter(sh=>sh.visualMode!=="programmatic"&&validShot(scene,sh,assets)).sort((a,b)=>a.inSec-b.inSec);
 if(keep.some((sh,i)=>i>0&&sh.inSec<keep[i-1].outSec-.001))throw Error("overlapping_verified_shots");
 const slots:{start:number;end:number;keep?:any}[]=[];
 const fill=(start:number,end:number)=>{
  const len=end-start;if(len<=.001)return;
  if(len<Math.min(1,duration)-.001)throw Error("gap_too_short_between_verified_shots");
  const count=Math.max(1,Math.ceil(len/5));
  for(let j=0;j<count;j++)slots.push({start:start+len*j/count,end:start+len*(j+1)/count});
 };
 let cursor=0;for(const sh of keep){fill(cursor,Number(sh.inSec));slots.push({start:sh.inSec,end:sh.outSec,keep:sh});cursor=Number(sh.outSec);}fill(cursor,duration);
 for(const slot of slots){
  if(slot.keep)continue;
  const q=exactQuote(scene,slot.start,slot.end);
  const matching=old.find(sh=>sh.visualMode==="programmatic"&&validShot(scene,sh,assets)&&near(sh.inSec,slot.start,.001)&&near(sh.outSec,slot.end,.001)&&sh.visualText===q);
  if(matching)slot.keep=matching;
 }
 let film=src;const changes:any[]=[];
 const apply=(name:string,args:any)=>{const p=applyOperation(film,name,args);film=p.film;changes.push({name,args});return p.result;};
 const ids=new Set(slots.filter(s=>s.keep).map(s=>s.keep.id));
 for(const sh of old)if(!ids.has(sh.id))apply("remove_shot",{shot_id:sh.id});
 const sequence:string[]=[];
 for(const slot of slots){
  if(slot.keep){sequence.push(slot.keep.id);continue;}
  const args={scene_id:sceneId,inSec:slot.start,outSec:slot.end,...focusArgs(scene,slot.start,slot.end)};
  sequence.push(apply("add_code_shot",args).shot_id);
 }
 const fixed=arr(film.scenes).find(s=>s.id===sceneId);
 const byId=new Map(arr(fixed.shots).map(sh=>[sh.id,sh]));
 fixed.shots=sequence.map((id,i)=>({...byId.get(id),order:i+1}));
 if(!sceneVisualReady(film,fixed))throw Error("timeline_repair_invalid");
 changes.push({name:"order_repaired_shots",args:{scene_id:sceneId,shot_ids:sequence}});
 return {film,changes};
}
export function chooseCandidate(results:any[],used:Set<string>,kind:string,seconds:number){
 return arr(results).find(x=>typeof x.result_id==="string"&&!used.has(x.result_id)&&x.license&&x.author&&x.url&&!/unknown|inconnue|non renseignée/i.test(String(x.license))&&(kind!=="video"||x.duration==null||Number(x.duration)>=seconds));
}
const durationOk=(n:number,target:number)=>Number.isFinite(n)&&n>0&&Math.abs(n-target)<=Math.max(2,target*.05);
const keyOf=(x:any)=>directorKey(x,0,0);
export async function structuredTick(admin:any,m:Mission,lease:any,row:Row,ctx:Ctx,brief:unknown,release:(status:string,error?:string|null,delay?:number)=>Promise<any>){
 const film=row.data,scenes=ordered(film.scenes);
 const {data,error}=await admin.from("production_tasks").select("kind,status,result,step_no").eq("mission_id",m.id).in("kind",kinds).order("step_no",{ascending:true}).limit(1000);
 if(error){await release("queued","structured_history_unavailable",20);return {status:"queued"};}
 const history:Ledger[]=data??[];
 const entries=(kind:string,key:string)=>history.filter(h=>h.kind===kind&&h.result?.key===key);
 const done=(kind:string,key:string)=>entries(kind,key).find(h=>h.status==="done");
 const count=(kind:string,key:string)=>entries(kind,key).filter(h=>!h.result?.transientProvider).length;
 const providerFailures=history.filter(h=>h.result?.transientProvider);
 const lastProvider=providerFailures.at(-1);
 if(lastProvider&&lastProvider.step_no===history.at(-1)?.step_no){
  const remaining=Math.ceil((Number(lastProvider.result.retryAt)-Date.now())/1000);
  if(remaining>0){await release("queued","provider_backoff",Math.min(900,remaining));return {status:"queued",phase:"provider_backoff"};}
  const consecutive=history.slice().reverse().findIndex(h=>!h.result?.transientProvider);
  const n=consecutive<0?history.length:consecutive;
  if(n>=6){await release("needs_review","provider_retry_exhausted");return {status:"needs_review",reason:"provider_retry_exhausted"};}
 }
 const block=async(code:string)=>{await release("needs_review",code);return {status:"needs_review",reason:code};};
 const step=async(kind:string,key:string,fn:()=>Promise<any>,extra:any={})=>{
  const {data:n,error:e}=await admin.rpc("begin_production_step",{...lease,p_kind:kind});if(e)throw Error(e.message);
  let result:any,ok=true;
  try{ctx.cfg.deadlineAt=Date.now()+75000;result=await fn();if(result?.ok===false)ok=false;}
  catch(e){ok=false;result={error:e instanceof Error?e.message.slice(0,700):String(e).slice(0,700)};}
  if(!ok&&/provider_(?:rate_limited|cooldown|temporarily_unavailable)|HTTP 429/i.test(String(result?.error??""))){const n=entries(kind,key).filter(h=>h.result?.transientProvider).length;result={...result,transientProvider:true,retryAt:Date.now()+Math.min(900,60*Math.pow(2,n))*1000};}
  const {error:finish}=await admin.rpc("finish_production_step",{...lease,p_step:n,p_ok:ok,p_result:{...result,...extra,key},p_render:null});if(finish)throw Error(finish.message);
  return {status:"advanced",phase:kind,ok};
 };
 const commit=async(next:Json,name:string,args:any)=>{
  if(JSON.stringify(next)===JSON.stringify(film))return {unchanged:true};
  const {data:saved,error:e}=await admin.rpc("save_film_operation",{p_user_id:m.user_id,p_film_id:row.id,p_rev:row.rev,p_data:next,p_op:{name,args}});
  if(e||!saved)throw Error("structured_revision_conflict");
  return {saved:true};
 };
 const opBatch=async(ops:{name:string;args:any}[],name:string)=>{
  let next=film;
  for(const op of ops)next=applyOperation(next,op.name,op.args).film;
  return commit(next,name,{operations:ops});
 };
 const call=async(name:string,props:any,prompt:string,input:any)=>{
  const tool:ToolDef={name,description:"Remet uniquement les données demandées, sans action.",input_schema:{type:"object",properties:props,required:Object.keys(props)}};
  const result=await complete(ctx.cfg,prompt,[{role:"user",content:JSON.stringify(input)}],[tool],4096,true);
  const chosen=result.toolCalls.filter(c=>c.name===name);
  if(chosen.length!==1||result.toolCalls.length!==1)throw Error("structured_model_response_invalid");
  await admin.from("usage_events").insert({user_id:m.user_id,kind:"llm_tokens",provider:ctx.cfg.provider+":"+ctx.cfg.model,units:result.usage.input+result.usage.output,cost_usd:0});
  return chosen[0].args;
 };
 const runTool=async(name:string,args:any)=>{
  const result=await execTool(ctx,name,args);
  if(result.metadata?.kind==="search_media"){
   const {error:e}=await admin.from("messages").insert({conversation_id:m.conversation_id,user_id:m.user_id,role:"tool",content:JSON.stringify(result.output),metadata:{...result.metadata,production_mission_id:m.id}});
   if(e)throw Error("search_result_persistence_failed");
  }
  if(ctx.usage.input+ctx.usage.output>0)await admin.from("usage_events").insert({user_id:m.user_id,kind:"llm_tokens",provider:ctx.cfg.provider+":"+ctx.cfg.model,units:ctx.usage.input+ctx.usage.output,cost_usd:0});
  return {...result.output,ok:!result.isError};
 };
 // 1. Fix the genre contract; a documentary must not silently become custom.
 const requestedType=/\b(documentaire|documentary)\b/i.test(m.goal)?"documentary":/\b(reportage)\b/i.test(m.goal)?"reportage":null;
 if(requestedType&&film.info?.type==="custom")return step("structured_project_type",requestedType,()=>opBatch([{name:"set_project_info",args:{type:requestedType}}],"structured_project_type"));
 // 2. Script planning is one scoped response, not a model-driven tool loop.
 const missing=scenes.find(s=>!String(s.narration?.text??"").trim());
 if(!scenes.length||missing){
  const key=missing?.id??"initial";
  if(count("structured_script",key)>=3)return block("script_planning_failed");
  return step("structured_script",key,async()=>{
   const target=missing?Number(missing.durationSec):m.target_seconds;
   const maxScenes=missing?1:Math.min(40,Math.max(1,Math.ceil(target/8)));
   const raw=await call("submit_script",{scenes:{type:"array",items:{type:"object",properties:{title:S,goal:S,text:S,seconds:N,mood:S},required:["title","goal","text","seconds","mood"]}}},"Écris le scénario audiovisuel demandé, narration prononçable et précise, progression et accroche. Respecte la durée totale et le nombre maximal de scènes. Environ deux à trois mots par seconde, sans remplissage. Si une scène existante est fournie, écris seulement celle-ci. Aucun fait inventé; les faits seront vérifiés. Une scène peut contenir plusieurs plans de 3–5 secondes. Ne modifie rien d'autre.",{goal:m.goal,plan:m.plan,brief,target,maxScenes,scene:missing??null});
   const list=arr(raw.scenes);
   if(!list.length||list.length>maxScenes||missing&&list.length!==1||list.some(s=>typeof s.text!=="string"||!s.text.trim()||typeof s.title!=="string"||typeof s.goal!=="string"||!Number.isFinite(s.seconds)||s.seconds<.5)||!durationOk(list.reduce((n,s)=>n+s.seconds,0),target))throw Error("script_contract_invalid");
   let next=film;const ids:string[]=[];
   for(const s of list){
    let id=missing?.id;
    if(!id){const added=applyOperation(next,"add_scene",{title:s.title,narrativeGoal:s.goal,durationSec:s.seconds,mood:s.mood});next=added.film;id=added.result.scene_id;}
    next=applyOperation(next,"set_scene_narration",{scene_id:id,text:s.text,targetDurationSec:missing?target:s.seconds}).film;ids.push(id);
   }
   await commit(next,"structured_script",{scene_ids:ids});return {sceneIds:ids};
  });
 }
 // 3. Verify facts BEFORE measuring voices. A revised text and its actual
 // supporting excerpts are committed together, never rewritten in a loop.
 const issues=researchIssues(film);
 if(issues.length){
  const scene=scenes.find(s=>issues.some(x=>x.startsWith("Scène "+s.id+" :")));
  if(!scene)return block("research_scope_missing");
  const key=scene.id;
  if(count("structured_research",key)>=3)return block("documentary_evidence_insufficient");
  const attempt=count("structured_research",key),qkey=key+":"+attempt;
  const q=done("structured_research_query",qkey);
  if(!q){
   if(count("structured_research_query",qkey)>=2)return block("research_query_failed");
   return step("structured_research_query",qkey,async()=>{
    const raw=await call("submit_queries",{query:S,englishQuery:S,alternateQuery:S},"Prépare trois requêtes documentaires courtes et ciblées sur les affirmations. La première dans la langue du récit, les deux autres en anglais, avec nom scientifique et termes d'articles scientifiques si utiles. Les deux requêtes anglaises doivent viser des travaux différents. Commence par une recherche large du sujet et de son mécanisme (2 à 5 mots), sans présupposer un chiffre exact; l’autre requête peut être plus précise. Réponds uniquement avec les requêtes.",{scene:scene.title,narration:scene.narration.text,goal:m.goal,previous:entries("structured_research",key).map(x=>x.result.error)});
    for(const k of ["query","englishQuery","alternateQuery"])if(typeof raw[k]!=="string"||!raw[k].trim()||raw[k].length>180)throw Error("invalid_research_query");
    return raw;
   });
  }
  return step("structured_research",key,async()=>{
   const r=await researchedNarration(ctx.cfg,scene.narration.text,q.result.query,q.result.englishQuery,q.result.alternateQuery,String(film.info?.language??"fr").split("-")[0],Number(scene.durationSec));
   let next=film;
   if(r.narration!==scene.narration.text)next=applyOperation(next,"set_scene_narration",{scene_id:scene.id,text:r.narration,targetDurationSec:scene.durationSec,language:scene.narration.language,voice:scene.narration.voice,ratePercent:scene.narration.ratePercent??0,pitchHz:scene.narration.pitchHz??0}).film;
   next=applyOperation(next,"record_documentary_review",{scene_id:scene.id,review:r.review}).film;
   if(researchIssues(next).some(x=>x.startsWith("Scène "+scene.id+" :")))throw Error("research_validation_failed");
   await commit(next,"structured_research",{scene_id:scene.id,review:r.review});
   await admin.from("usage_events").insert({user_id:m.user_id,kind:"llm_tokens",provider:ctx.cfg.provider+":"+ctx.cfg.model,units:r.usage.input+r.usage.output,cost_usd:0});
   return {sceneId:scene.id,sourceCount:r.sourceCount,claims:r.review.claims.length};
  });
 }
 // 4. Measure real voice once per unique text and vocal configuration.
 const voiceKey=await keyOf(scenes.map(s=>({id:s.id,text:s.narration.text,voice:s.narration.voice,language:s.narration.language,rate:s.narration.ratePercent??0,pitch:s.narration.pitchHz??0})));
 const allMeasured=scenes.every(s=>Number.isFinite(s.narration.measuredDurationSec)&&s.narration.measuredDurationSec>0&&near(Number(s.durationSec),s.narration.measuredDurationSec,.001));
 const measured=allMeasured?scenes.map(s=>({sceneId:s.id,durationSec:s.narration.measuredDurationSec,targetDurationSec:s.narration.targetDurationSec,ttsProvider:s.narration.ttsProvider})):done("structured_voice_measure",voiceKey)?.result?.segments;
 if(!Array.isArray(measured)){
  if(count("structured_voice_measure",voiceKey)>=2)return block("voice_measurement_failed");
  return step("structured_voice_measure",voiceKey,()=>runTool("measure_narration",{}));
 }
 if(measured.length!==scenes.length||new Set(measured.map(x=>x.sceneId)).size!==scenes.length||measured.some(x=>!scenes.some(s=>s.id===x.sceneId)||!Number.isFinite(x.durationSec)||x.durationSec<.5))return block("voice_measurement_invalid");
 const total=measured.reduce((n,x)=>n+x.durationSec,0);
 if(!durationOk(total,m.target_seconds)){
  const attempts=history.filter(h=>h.kind==="structured_voice_rate").length;
  if(attempts>=2)return block("voice_duration_out_of_range");
  const ops=scenes.map(s=>{const old=Number(s.narration.ratePercent??0),rate=Math.max(-20,Math.min(20,Math.round((100+old)*total/m.target_seconds-100)));return {name:"set_scene_narration",args:{scene_id:s.id,text:s.narration.text,targetDurationSec:s.durationSec,voice:s.narration.voice,language:s.narration.language,pitchHz:s.narration.pitchHz??0,ratePercent:rate}};});
  if(ops.every((o,i)=>o.args.ratePercent===(scenes[i].narration.ratePercent??0)))return block("voice_duration_out_of_range");
  return step("structured_voice_rate",voiceKey,()=>opBatch(ops,"structured_voice_rate"),{actualSeconds:total,targetSeconds:m.target_seconds});
 }
 const targetAligned=allMeasured&&scenes.every(s=>near(Number(s.narration.targetDurationSec),Number(s.narration.measuredDurationSec),.001));
 if(!targetAligned){
  if(count("structured_voice_align",voiceKey)>=2)return block("voice_alignment_failed");
  return step("structured_voice_align",voiceKey,()=>opBatch([{name:"align_narration_durations",args:{segments:measured,acceptMeasuredTargets:true}}],"structured_voice_align"));
 }
 // 5. Fixed visual timeline, then creative decisions on each scene's exact
 // slots. Media attempts are bounded per shot; code fallback is literal.
 const assets=assetMap(film);
 for(const scene of scenes){
  const layoutKey=await keyOf({sceneId:scene.id,text:scene.narration.text,duration:scene.durationSec,slots:ordered(scene.shots).map(sh=>[sh.id,sh.inSec,sh.outSec])});
  const plan=done("structured_visual_plan",layoutKey);
  if(!plan&&!sceneVisualReady(film,scene)){
   if(count("structured_visual_layout",layoutKey)>=2)return block("visual_layout_unrepairable");
   return step("structured_visual_layout",layoutKey,async()=>{
    const fixed=repairSceneLayout(film,scene.id);
    await commit(fixed.film,"structured_visual_layout",{scene_id:scene.id,changes:fixed.changes});
    return {sceneId:scene.id,operations:fixed.changes.length};
   });
  }
  if(!plan){
   if(count("structured_visual_plan",layoutKey)>=3)return block("visual_direction_unavailable");
   return step("structured_visual_plan",layoutKey,async()=>{
    const codeShots=ordered(scene.shots).filter(sh=>sh.visualMode==="programmatic");
    if(!codeShots.length)return {sceneId:scene.id,targets:[]};
    const raw=await call("submit_visual_plan",{targets:{type:"array",items:{type:"object",properties:{shotId:S,mode:{type:"string",enum:["media","code"]},query:S,alternateQuery:S,kind:{type:"string",enum:["image","video"]},intent:S,visualType:S,visualItems:{type:"array",items:S}},required:["shotId","mode","query","alternateQuery","kind","intent","visualType","visualItems"]}}},"Pour CHAQUE plan proposé, choisis un vrai média quand le contenu est observable directement et un schéma quand il est abstrait. Pour un média, indique deux requêtes visuelles différentes et concrètes, de préférence en anglais, et l'intention visible exacte. Un plan de guépard marchant ne démontre pas une course. Pour code, choisis focus, steps, timeline, comparison ou cause_effect uniquement si la citation le justifie; visualItems sont des extraits exacts et ordonnés de la citation. Ne change ni récit, ni durée, ni identifiant. Aucune source inventée. Aucun quota artificiel par scène. Un film complet doit contenir des médias réels pertinents vérifiés.",{goal:m.goal,brief,scene:scene.title,narration:scene.narration.text,shots:codeShots.map(sh=>({shotId:sh.id,quote:sh.visualText,seconds:sh.outSec-sh.inSec}))});
    const targets=arr(raw.targets);
    if(targets.length!==codeShots.length||new Set(targets.map(x=>x.shotId)).size!==codeShots.length||targets.some(x=>!codeShots.some(sh=>sh.id===x.shotId)||!["media","code"].includes(x.mode)||x.mode==="media"&&(!["image","video"].includes(x.kind)||typeof x.query!=="string"||!x.query.trim()||x.query.length>200||typeof x.alternateQuery!=="string"||x.alternateQuery.length>200||typeof x.intent!=="string"||x.intent.trim().length<10)))throw Error("visual_plan_contract_invalid");
    let next=film;const final:any[]=[];
    for(const x of targets){
     const sh=codeShots.find(sh=>sh.id===x.shotId);
     if(x.mode==="code"){
      // Creative diagram enrichment is optional, but exact validation is mandatory.
      if(typeof x.visualType==="string"&&Array.isArray(x.visualItems)&&x.visualItems.length){
       try{next=applyOperation(next,"set_motion_visual",{shot_id:sh.id,visualType:x.visualType,visualItems:x.visualItems}).film;}catch{/* retain validated original */}
      }
     }else final.push({shotId:sh.id,quote:sh.visualText,query:x.query.trim(),alternateQuery:x.alternateQuery.trim(),kind:x.kind,intent:x.intent.trim().slice(0,350),originalSpec:sh.visualSpec??null,originalStyle:sh.cardStyle??"focus"});
    }
    await commit(next,"structured_visual_plan",{scene_id:scene.id,targets:final.map(x=>x.shotId)});
    return {sceneId:scene.id,targets:final};
   });
  }
  for(const target of arr(plan.result.targets)){
   const sh=arr(scene.shots).find(s=>s.id===target.shotId);
   if(!sh)return block("visual_target_missing");
   if(verifiedVisualEvidence(scene,sh,assets.get(sh.mediaRef)))continue;
   const slotKey=layoutKey+":"+sh.id;
   if(done("structured_media_fallback",slotKey))continue;
   const attempts=entries("structured_media_attach",slotKey);
   const verified=entries("structured_media_verify",slotKey);
   const last=attempts.at(-1);
   if(last?.status==="done"&&sh.mediaRef===last.result.media_asset_id&&!verified.some(x=>x.result.candidateId===last.result.candidateId)){
    return step("structured_media_verify",slotKey,()=>runTool("verify_shot_media",{shot_id:sh.id,narrationQuote:target.quote,visualIntent:target.intent}),{candidateId:last.result.candidateId});
   }
   const used=new Set<string>(attempts.map(x=>String(x.result.candidateId)));
   // Try distinct assets in two independent searches; never retry the same rejected asset.
   if(attempts.length<3){
    for(let n=0;n<2;n++){
     const searchKey=slotKey+":"+n;
     const search=done("structured_media_search",searchKey);
     const kind=n===0?target.kind:(target.kind==="video"?"image":"video");
     if(!search){
      if(count("structured_media_search",searchKey)>=2)continue;
      const query=n===0?target.query:(target.alternateQuery||target.query);
      return step("structured_media_search",searchKey,()=>runTool("search_media",{query,kind,limit:8}),{shotId:sh.id,kind,query});
     }
     const candidate=chooseCandidate(search.result.results,used,kind,Number(sh.outSec)-Number(sh.inSec));
     if(candidate){
      return step("structured_media_attach",slotKey,()=>runTool("add_found_media",{shot_id:sh.id,result_id:candidate.result_id}),{candidateId:candidate.result_id});
     }
    }
   }
   if(count("structured_media_fallback",slotKey)>=2)return block("visual_fallback_failed");
   return step("structured_media_fallback",slotKey,async()=>{
    const args:any={shot_id:sh.id,visualText:target.quote,cardStyle:target.originalStyle??"focus"};
    if(target.originalSpec){args.visualType=target.originalSpec.type;args.visualItems=arr(target.originalSpec.items).map(x=>x.text);}
    const result=await runTool("turn_shot_into_code",args);
    return {...result,reason:"distinct_media_candidates_exhausted"};
   });
  }
 }
 // 6. Do not dispatch a code-only movie or one with failed semantic gates.
 if(!auditFoundations(film).verifiedRealShots)return block("no_relevant_real_media_verified");
 if(scenes.some(s=>!sceneVisualReady(film,s)))return block("visual_timeline_invalid");
 // Subtitles requested explicitly: estimate cues from the measured scene
 // timings. The render engine can align more precisely when supported.
 if(/\b(sous[- ]titres?|subtitles?|captions?)\b/i.test(m.goal)&&!/\b(sans sous[- ]titres?|without subtitles?)\b/i.test(m.goal)&&!arr(film.subtitles).some(t=>arr(t.cues).length)){
  const key=await keyOf(scenes.map(s=>[s.id,s.narration.text,s.durationSec]));
  if(count("structured_subtitles",key)>=2)return block("subtitle_preparation_failed");
  return step("structured_subtitles",key,async()=>{
   let offset=0;const cues:any[]=[];
   for(const scene of scenes){for(const b of planNarrativeBeats(scene.narration.text,scene.durationSec))cues.push({startSec:offset+b.startSec,endSec:offset+b.endSec,text:b.quote});offset+=scene.durationSec;}
   return opBatch([{name:"update_subtitles",args:{language:film.info?.language??"fr",cues}}],"structured_subtitles");
  });
 }
 return null; // montage and independent reviews are still performed by productionTick.
}

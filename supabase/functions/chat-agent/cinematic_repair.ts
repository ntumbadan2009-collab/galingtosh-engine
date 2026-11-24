import { applyOperation } from "./film.ts";
import {auditFoundations} from "./foundations.ts";
import { narrativePreflight } from "./narrative.ts";
import { editorialTimelineIssues } from "./editorial.ts";

export function candidateRepairs(snapshot:any,reports:any[]):{film:any;ids:string[]}|null {
  let film=structuredClone(snapshot);
  const rejected=reports.filter(r=>r.passed===false);
  if(!rejected.length)return null;
  const ids:string[]=[];
  for(const r of rejected){
    const verdict=r.evidence?.verdict;
    if(!Array.isArray(verdict)||!verdict.length)return null;
    for(const v of verdict){
      const states=[v.relevance,v.readability,v.composition];
      if(states.some(x=>!["pass","fail","uncertain"].includes(x)||x==="uncertain"))return null;
      if(!states.includes("fail"))continue;
      if(typeof v.shotId!=="string"||ids.includes(v.shotId))return null;
      const scene=film.scenes?.find((s:any)=>s.shots?.some((sh:any)=>sh.id===v.shotId));
      const shot=scene?.shots?.find((sh:any)=>sh.id===v.shotId);
      if(!shot || (shot.visualMode==="programmatic"&&!shot.visualSpec))return null;
      const quote=shot.visualMode==="programmatic"?shot.visualText:shot.visualEvidence?.narrationQuote;
      if(typeof quote!=="string"||Number(shot.outSec)-Number(shot.inSec)>12)return null;
      try{
        film=applyOperation(film,"turn_shot_into_code",{shot_id:v.shotId,visualText:quote,cardStyle:"focus"}).film;
      }catch{return null;}
      ids.push(v.shotId);
      if(ids.length>3)return null;
    }
  }
  if(!ids.length||narrativePreflight(film).length||editorialTimelineIssues(film).length)return null;
  return {film,ids};
}

// The RPC commits a single bounded retry atomically, refusing edits made
// after the reviewed render and any pending cancellation or pause.
export async function attemptCinematicRepair(admin:any,mission:any,snapshot:any):Promise<boolean>{
  const {data:reports,error}=await admin.from("quality_reports").select("passed,evidence")
    .eq("mission_id",mission.id).eq("render_job_id",mission.render_job_id).like("check_name","level4_visual_%").eq("passed",false);
  if(error)return false;
  const plan=candidateRepairs(snapshot,reports??[]);
  if(!plan||!auditFoundations(plan.film).passed)return false;
  const {data,error:retryError}=await admin.rpc("retry_cinematic_repair",{
    p_mission_id:mission.id,p_lease:mission.lease_token,p_render:mission.render_job_id,p_ids:plan.ids
  });
  if(retryError)throw Error("cinematic_repair_transaction_unavailable");
  return typeof data==="string"&&data.length>0;
}

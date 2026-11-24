-- Offline migration candidate; run in isolated staging before deployment.
-- One conservative, atomic retry. Never accept a complete film from a model.
begin;
create or replace function public.retry_cinematic_repair(p_mission_id uuid,p_lease uuid,p_render uuid,p_ids text[])
returns uuid language plpgsql security invoker set search_path='' as $$
declare m public.production_missions; r public.render_jobs; f public.films; snapshot jsonb;
 repaired jsonb; sc jsonb; sh jsonb; path text[]; si integer; pi integer;
 quote text; narrative text; sid text; found_ids text[]:=array[]::text[]; j uuid;
begin
 select * into m from public.production_missions where id=p_mission_id and lease_token=p_lease
   and lease_until>now() and status='waiting_render' and render_job_id=p_render for update;
 if not found then raise exception 'Invalid mission lease'; end if;
 if m.requested_action is not null or m.step_count>=m.max_steps or
    exists(select 1 from public.production_tasks where mission_id=m.id and kind='cinematic_repair') then return null; end if;
 if cardinality(p_ids) is null or cardinality(p_ids) not between 1 and 3 or
    cardinality(p_ids)<>(select count(distinct id) from unnest(p_ids) id) then return null; end if;
 select * into r from public.render_jobs where id=p_render and project_id=m.project_id and user_id=m.user_id and status='done';
 if not found then return null; end if;
 -- All requested targets must have a concrete failure in this exact render's recorded review.
 foreach sid in array p_ids loop
  if not exists(select 1 from public.quality_reports q cross join lateral jsonb_array_elements(q.evidence->'verdict') v
   where q.mission_id=m.id and q.render_job_id=r.id and q.check_name like 'level4_visual_%' and not q.passed
   and v->>'shotId'=sid and 'fail' in (v->>'relevance',v->>'readability',v->>'composition')
   and v->>'relevance' in ('pass','fail') and v->>'readability' in ('pass','fail') and v->>'composition' in ('pass','fail')) then return null; end if;
 end loop;
 perform 1 from public.projects where id=m.project_id and user_id=m.user_id for update;
 if not found then return null; end if;
 if exists(select 1 from public.render_jobs where project_id=m.project_id and status in ('queued','running')) then return null; end if;
 select data into snapshot from public.films where project_id=m.project_id and user_id=m.user_id and version=r.film_version;
 if not found or snapshot->'info'->>'editorialLevel' not in ('4','5') or snapshot->'info'->>'visualPolicy'<>'strict' then return null; end if;
 select * into f from public.films where project_id=m.project_id and user_id=m.user_id order by version desc limit 1 for update;
 if not found or f.data is distinct from snapshot or f.rev<>0 then return null; end if;
 repaired:=snapshot;
 for si in 0..jsonb_array_length(snapshot->'scenes')-1 loop
  sc:=snapshot->'scenes'->si;
  for pi in 0..jsonb_array_length(sc->'shots')-1 loop
   sh:=sc->'shots'->pi;
   sid:=sh->>'id';
   if not (sid=any(p_ids)) then continue; end if;
   if sid=any(found_ids) or (sh->>'visualMode'='programmatic' and not (sh?'visualSpec')) then return null; end if;
   quote:=case when sh->>'visualMode'='programmatic' then sh->>'visualText' else sh->'visualEvidence'->>'narrationQuote' end;
   narrative:=coalesce(sc->'narration'->>'text',sc->>'narrativeGoal');
   if quote is null or char_length(trim(quote)) not between 5 and 280 or narrative is null
      or strpos(narrative,quote)=0 or (sh->>'outSec')::numeric-(sh->>'inSec')::numeric not between 1 and 12 then return null; end if;
   sh:=(sh-'mediaRef'-'sourceInSec'-'visualEvidence'-'visualSpec')||
       jsonb_build_object('visualMode','programmatic','visualText',quote,'cardStyle','focus','camera',jsonb_build_object('type','ken_burns'));
   path:=array['scenes',si::text,'shots',pi::text];
   repaired:=jsonb_set(repaired,path,sh,false);
   found_ids:=array_append(found_ids,sid);
  end loop;
 end loop;
 if cardinality(found_ids)<>cardinality(p_ids) then return null; end if;
 if not public.save_film_operation(m.user_id,f.id,f.rev,repaired,jsonb_build_object('name','cinematic_repair','args',jsonb_build_object('shot_ids',p_ids))) then return null; end if;
 j:=public.queue_render(m.user_id,m.project_id);
 if j is null or j=r.id then raise exception 'Retry job not created'; end if;
 insert into public.production_tasks(mission_id,step_no,kind,status,result,finished_at)
 values(m.id,m.step_count+1,'cinematic_repair','done',jsonb_build_object('previous_render',r.id,'new_render',j,'shot_ids',p_ids),now());
 update public.production_missions set render_job_id=j,step_count=step_count+1,lease_token=null,lease_until=null,
 retry_count=0,error_code=null,available_at=now()+interval '2 seconds',updated_at=now() where id=m.id;
 insert into public.production_events(mission_id,kind,detail) values(m.id,'cinematic_repair','Plans rejetés remplacés par des citations exactes; nouveau rendu à contrôler.');
 return j;
end $$;
revoke execute on function public.retry_cinematic_repair(uuid,uuid,uuid,text[]) from public,anon,authenticated;
grant execute on function public.retry_cinematic_repair(uuid,uuid,uuid,text[]) to service_role;
commit;

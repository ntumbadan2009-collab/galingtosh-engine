-- Independent SQL delivery gate for level 4/5. Stage before applying.
begin;
create or replace function public.enforce_cinematic_delivery()
returns trigger language plpgsql security invoker set search_path='' as $$
declare r public.render_jobs; snapshot jsonb; batches jsonb; batch jsonb; idx integer:=0;
 expected integer; seen integer:=0; n integer; name text;
begin
 if new.status<>'done' or old.status='done' then return new; end if;
 select * into r from public.render_jobs where id=new.render_job_id and project_id=new.project_id and user_id=new.user_id and status='done';
 if not found then raise exception 'Rendu final indisponible'; end if;
 select data into snapshot from public.films where project_id=new.project_id and user_id=new.user_id and version=r.film_version;
 if not found then raise exception 'Version rendue indisponible'; end if;
 if coalesce(snapshot->'info'->>'editorialLevel','') not in ('4','5') then return new; end if;
 if r.technical_report->'editorial_quality'->'passed' is distinct from 'true'::jsonb
    or r.technical_report->>'editorial_level' is distinct from snapshot->'info'->>'editorialLevel'
    or r.technical_report->'cinematic_review'->>'sampling' is distinct from 'two_final_frames_per_shot'
 then raise exception 'Contrôle cinématographique manquant'; end if;
 batches:=r.technical_report->'cinematic_review'->'batches';
 if jsonb_typeof(batches) is distinct from 'array' or jsonb_array_length(batches) not between 1 and 80
 then raise exception 'Lots visuels manquants'; end if;
 select count(*) into expected from jsonb_array_elements(snapshot->'scenes') s cross join lateral jsonb_array_elements(s->'shots') sh;
 for batch in select value from jsonb_array_elements(batches) loop
   if batch->>'index' is distinct from idx::text or coalesce(batch->>'count','') not in ('1','2','3')
   then raise exception 'Lot invalide'; end if;
   n:=(batch->>'count')::int;
   name:='level4_visual_'||lpad(idx::text,3,'0');
   if exists(select 1 from public.quality_reports q where q.mission_id=new.id and q.render_job_id=r.id and q.check_name=name and not q.passed)
    or not exists(select 1 from public.quality_reports q where q.mission_id=new.id and q.render_job_id=r.id and q.check_name=name and q.passed
       and q.evidence->>'sampling'='two_final_frames_per_shot' and jsonb_typeof(q.evidence->'verdict')='array'
       and jsonb_array_length(q.evidence->'verdict')=n
       and not exists(select 1 from jsonb_array_elements(q.evidence->'verdict') v where
         v->>'relevance' is distinct from 'pass' or v->>'readability' is distinct from 'pass' or v->>'composition' is distinct from 'pass'))
   then raise exception 'Lot visuel % non validé',idx; end if;
   seen:=seen+n;idx:=idx+1;
 end loop;
 if seen<>expected then raise exception 'Couverture visuelle incomplète'; end if;
 return new;
end $$;
revoke execute on function public.enforce_cinematic_delivery() from public,anon,authenticated;
grant execute on function public.enforce_cinematic_delivery() to service_role;
drop trigger if exists cinematic_delivery_gate on public.production_missions;
create trigger cinematic_delivery_gate before update of status on public.production_missions
for each row execute function public.enforce_cinematic_delivery();
commit;

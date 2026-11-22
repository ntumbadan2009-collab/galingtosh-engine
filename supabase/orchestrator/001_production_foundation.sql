-- Additive, isolated foundation for durable production. No existing films or jobs are changed.
begin;
alter table public.render_jobs add column if not exists technical_report jsonb;
create table public.production_missions (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 project_id uuid not null references public.projects(id) on delete cascade,
 conversation_id uuid not null references public.conversations(id) on delete cascade,
 request_id uuid not null,
 goal text not null check(char_length(goal) between 1 and 8000),
 plan text not null check(char_length(plan) between 1 and 16000),
 target_seconds integer not null check(target_seconds between 1 and 3600),
 status text not null default 'draft' check(status in ('draft','queued','running','waiting_render','paused','needs_review','done','failed','canceled')),
 approved_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 available_at timestamptz not null default now(),
 lease_token uuid,
 lease_until timestamptz,
 step_count integer not null default 0 check(step_count>=0),
 max_steps integer not null default 240 check(max_steps between 1 and 1000),
 retry_count integer not null default 0 check(retry_count>=0),
 render_job_id uuid references public.render_jobs(id) on delete set null,
 checkpoint jsonb not null default '{}'::jsonb,
 error_code text,
 unique(user_id,request_id)
);
create unique index production_one_active_project on public.production_missions(project_id)
 where status in ('queued','running','waiting_render','paused','needs_review');
create index production_claim_idx on public.production_missions(available_at,created_at) where status in ('queued','running','waiting_render');
create index production_owner_idx on public.production_missions(user_id,created_at desc);
create table public.production_tasks (
 id uuid primary key default gen_random_uuid(),
 mission_id uuid not null references public.production_missions(id) on delete cascade,
 step_no integer not null check(step_no>0),
 kind text not null,
 status text not null check(status in ('started','done','failed','uncertain')),
 result jsonb not null default '{}'::jsonb,
 started_at timestamptz not null default now(),
 finished_at timestamptz,
 unique(mission_id,step_no)
);
create table public.production_events (
 id bigint generated always as identity primary key,
 mission_id uuid not null references public.production_missions(id) on delete cascade,
 kind text not null,
 detail text not null check(char_length(detail)<=1000),
 created_at timestamptz not null default now()
);
create index production_event_order_idx on public.production_events(mission_id,id);
create table public.production_segments (
 id uuid primary key default gen_random_uuid(),
 mission_id uuid not null references public.production_missions(id) on delete cascade,
 ordinal integer not null check(ordinal>0),
 film_version integer not null,
 start_seconds numeric not null check(start_seconds>=0),
 duration_seconds numeric not null check(duration_seconds>0),
 status text not null default 'planned' check(status in ('planned','rendering','ready','failed')),
 output_path text,
 checksum text,
 unique(mission_id,ordinal)
);
create table public.quality_reports (
 id uuid primary key default gen_random_uuid(),
 mission_id uuid not null references public.production_missions(id) on delete cascade,
 render_job_id uuid references public.render_jobs(id) on delete set null,
 check_name text not null,
 passed boolean not null,
 evidence jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
alter table public.production_missions enable row level security;
alter table public.production_tasks enable row level security;
alter table public.production_events enable row level security;
alter table public.production_segments enable row level security;
alter table public.quality_reports enable row level security;
revoke all on public.production_missions,public.production_tasks,public.production_events,public.production_segments,public.quality_reports from public,anon,authenticated;
grant select on public.production_missions,public.production_tasks,public.production_events,public.production_segments,public.quality_reports to authenticated;
grant all on public.production_missions,public.production_tasks,public.production_events,public.production_segments,public.quality_reports to service_role;
grant usage,select on sequence public.production_events_id_seq to service_role;
create policy mission_owner_read on public.production_missions for select to authenticated using(user_id=(select auth.uid()));
create policy task_owner_read on public.production_tasks for select to authenticated using(exists(select 1 from public.production_missions m where m.id=mission_id and m.user_id=(select auth.uid())));
create policy event_owner_read on public.production_events for select to authenticated using(exists(select 1 from public.production_missions m where m.id=mission_id and m.user_id=(select auth.uid())));
create policy segment_owner_read on public.production_segments for select to authenticated using(exists(select 1 from public.production_missions m where m.id=mission_id and m.user_id=(select auth.uid())));
create policy quality_owner_read on public.quality_reports for select to authenticated using(exists(select 1 from public.production_missions m where m.id=mission_id and m.user_id=(select auth.uid())));

create function public.approve_production(p_mission_id uuid,p_user_id uuid)
returns uuid language plpgsql security invoker set search_path='' as $$
declare m public.production_missions;
begin
 select * into m from public.production_missions where id=p_mission_id and user_id=p_user_id for update;
 if not found then raise exception 'Mission introuvable'; end if;
 if m.status in ('queued','running','waiting_render','done') then return m.id; end if;
 if m.status<>'draft' then raise exception 'Mission non approuvable'; end if;
 if not exists(select 1 from public.projects where id=m.project_id and user_id=m.user_id)
 or not exists(select 1 from public.conversations where id=m.conversation_id and project_id=m.project_id and user_id=m.user_id) then raise exception 'Périmètre invalide'; end if;
 if m.target_seconds>600 then raise exception 'Durée supérieure à la capacité actuelle du moteur'; end if;
 if exists(select 1 from public.render_jobs where project_id=m.project_id and status in ('queued','running')) then raise exception 'Une production vidéo est déjà en cours'; end if;
 update public.production_missions set status='queued',approved_at=now(),updated_at=now(),available_at=now() where id=m.id;
 insert into public.production_events(mission_id,kind,detail) values(m.id,'approved','Plan approuvé. Mission mise en file.');
 return m.id;
end $$;

create function public.claim_production()
returns setof public.production_missions language plpgsql security invoker set search_path='' as $$
declare m public.production_missions;
begin
 -- A crash during a side-effect cannot be blindly replayed. Explicit reconciliation is required.
 with expired as (
 update public.production_missions x set status='needs_review',lease_token=null,lease_until=null,updated_at=now(),error_code='uncertain_tool'
 where x.status='running' and x.lease_until<now() and exists(select 1 from public.production_tasks t where t.mission_id=x.id and t.status='started')
 returning x.id
 ), marked as (
 update public.production_tasks t set status='uncertain',finished_at=now() from expired e where t.mission_id=e.id and t.status='started'
 )
 insert into public.production_events(mission_id,kind,detail) select id,'needs_review','Interruption pendant une opération : vérification nécessaire avant reprise.' from expired;
 select * into m from public.production_missions x
 where x.approved_at is not null and x.available_at<=now()
 and x.status in ('queued','running','waiting_render')
 and (x.lease_until is null or x.lease_until<now())
 order by x.available_at,x.created_at for update skip locked limit 1;
 if not found then return; end if;
 return query update public.production_missions set status=case when m.status='waiting_render' then 'waiting_render' else 'running' end,
 lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes',updated_at=now()
 where id=m.id returning *;
end $$;

create function public.begin_production_step(p_mission_id uuid,p_lease uuid,p_kind text)
returns integer language plpgsql security invoker set search_path='' as $$
declare n integer;
begin
 update public.production_missions set step_count=step_count+1,updated_at=now()
 where id=p_mission_id and lease_token=p_lease and lease_until>now() and status='running' and step_count<max_steps
 returning step_count into n;
 if not found then raise exception 'Bail ou budget de mission expiré'; end if;
 insert into public.production_tasks(mission_id,step_no,kind,status) values(p_mission_id,n,left(p_kind,100),'started');
 insert into public.production_events(mission_id,kind,detail) values(p_mission_id,'step_started',left(p_kind,100));
 return n;
end $$;

create function public.finish_production_step(p_mission_id uuid,p_lease uuid,p_step integer,p_ok boolean,p_result jsonb,p_render uuid default null)
returns void language plpgsql security invoker set search_path='' as $$
declare m public.production_missions;
begin
 select * into m from public.production_missions where id=p_mission_id and status='running' and lease_token=p_lease and lease_until>now() for update;
 if not found then raise exception 'Bail expiré'; end if;
 if p_render is not null and not exists(select 1 from public.render_jobs where id=p_render and project_id=m.project_id and user_id=m.user_id) then raise exception 'Rendu hors périmètre'; end if;
 update public.production_tasks set status=case when p_ok then 'done' else 'failed' end, result=coalesce(p_result,'{}'::jsonb),finished_at=now()
 where mission_id=m.id and step_no=p_step and status='started';
 if not found then raise exception 'Étape introuvable ou déjà enregistrée'; end if;
 update public.production_missions set status=case when p_render is not null and p_ok then 'waiting_render' else 'queued' end,
 render_job_id=coalesce(p_render,render_job_id),checkpoint=jsonb_build_object('last_step',p_step,'ok',p_ok),retry_count=0,
 lease_token=null,lease_until=null,available_at=now()+interval '2 seconds',updated_at=now()
 where id=m.id;
 insert into public.production_events(mission_id,kind,detail) values(m.id,case when p_ok then 'step_done' else 'step_failed' end,case when p_ok then 'Opération confirmée.' else 'Opération échouée.' end);
end $$;

create function public.release_production(p_mission_id uuid,p_lease uuid,p_status text,p_error text default null,p_delay integer default 15)
returns void language plpgsql security invoker set search_path='' as $$
declare m public.production_missions;
begin
 if p_status not in ('queued','waiting_render','paused','needs_review','failed','done','canceled') then raise exception 'État invalide'; end if;
 select * into m from public.production_missions where id=p_mission_id and lease_token=p_lease and lease_until>now() for update;
 if not found then raise exception 'Bail expiré'; end if;
 if exists(select 1 from public.production_tasks where mission_id=m.id and status='started') then
  raise exception 'Étape en cours non réconciliée';
 end if;
 if p_status='done' and not exists(select 1 from public.render_jobs r join storage.objects o on o.bucket_id='renders' and o.name=r.output_path where r.id=m.render_job_id and r.project_id=m.project_id and r.user_id=m.user_id and r.status='done'
 and jsonb_typeof(r.technical_report->'duration_seconds')='number'
 and abs((r.technical_report->>'duration_seconds')::numeric-m.target_seconds)<=greatest(2,m.target_seconds*0.05)
 and coalesce((r.technical_report->>'width')::integer,0)>0 and coalesce((r.technical_report->>'height')::integer,0)>0
 ) then raise exception 'Fichier final absent ou contrôle technique non validé'; end if;
 update public.production_missions set status=p_status,error_code=left(p_error,100),lease_token=null,lease_until=null,
 available_at=now()+make_interval(secs=>greatest(2,least(p_delay,900))),retry_count=case when p_error is not null then retry_count+1 else retry_count end,updated_at=now() where id=m.id;
 if p_status not in ('queued','waiting_render') then insert into public.production_events(mission_id,kind,detail) values(m.id,p_status,coalesce(left(p_error,100),p_status)); end if;
end $$;

revoke execute on function public.approve_production(uuid,uuid),public.claim_production(),public.begin_production_step(uuid,uuid,text),public.finish_production_step(uuid,uuid,integer,boolean,jsonb,uuid),public.release_production(uuid,uuid,text,text,integer) from public,anon,authenticated;
grant execute on function public.approve_production(uuid,uuid),public.claim_production(),public.begin_production_step(uuid,uuid,text),public.finish_production_step(uuid,uuid,integer,boolean,jsonb,uuid),public.release_production(uuid,uuid,text,text,integer) to service_role;
commit;

-- Additive repair: preserve projects, films and history.
alter policy conversations_update_own on public.conversations with check (
(select auth.uid()) = user_id and (project_id is null or exists(select 1 from public.projects p where p.id=conversations.project_id and p.user_id=(select auth.uid()))));
revoke update on public.profiles from authenticated, anon;
grant update(display_name,avatar_url) on public.profiles to authenticated;
alter policy media_assets_insert_own on public.media_assets with check (
user_id=(select auth.uid()) and source='upload' and split_part(storage_path,'/',1)=(select auth.uid())::text
and storage_path !~ '(^|/)\.\.?(/|$)' and storage_path not like '%//%'
and exists(select 1 from public.projects p where p.id=project_id and p.user_id=(select auth.uid())));

create or replace function public.create_studio_project(p_title text, p_synopsis text default '') returns public.projects
language plpgsql security definer set search_path='' as $$
declare p public.projects; u uuid := auth.uid();
begin
 if u is null then raise exception 'authentication_required'; end if;
 if length(trim(p_title)) not between 1 and 200 or length(p_synopsis)>4000 then raise exception 'invalid_project'; end if;
 insert into public.projects(user_id,title,type) values(u,trim(p_title),'custom') returning * into p;
 insert into public.films(project_id,user_id,version,data) values(p.id,u,1,jsonb_build_object(
 'info',jsonb_build_object('title',p.title,'type',p.type,'language','fr','synopsis',p_synopsis),
 'format','{"aspect":"16:9","width":1920,"height":1080,"fps":30}'::jsonb,
 'scenes','[]'::jsonb,'characters','[]'::jsonb,'media','[]'::jsonb,'audio','{"tracks":[]}'::jsonb,
 'effects','[]'::jsonb,'transitions','[]'::jsonb,'subtitles','[]'::jsonb,
 'render','{"resolution":"1080p","audioBitrateKbps":192,"videoBitrateMbps":8}'::jsonb));
 return p;
end $$;
revoke all on function public.create_studio_project(text,text) from public,anon;
grant execute on function public.create_studio_project(text,text) to authenticated;

-- Shared project lock serializes film editing, undo and render snapshots.
create or replace function public.save_film_operation(p_user_id uuid,p_film_id uuid,p_rev integer,p_data jsonb,p_op jsonb)
returns boolean language plpgsql security definer set search_path='' as $$
declare f public.films; pid uuid;
begin
 select project_id into pid from public.films where id=p_film_id and user_id=p_user_id;
 if pid is null then raise exception 'film_not_found'; end if;
 perform 1 from public.projects where id=pid and user_id=p_user_id for update;
 select * into f from public.films where project_id=pid order by version desc limit 1 for update;
 if f.id<>p_film_id or f.rev<>p_rev then return false; end if;
 update public.films set data=p_data,rev=rev+1 where id=f.id;
 insert into public.film_operations(film_id,user_id,op,snapshot_before) values(f.id,p_user_id,p_op,f.data);
 update public.projects set title=coalesce(p_data->'info'->>'title',title),type=coalesce(p_data->'info'->>'type',type),updated_at=now() where id=pid;
 return true;
end $$;
revoke all on function public.save_film_operation(uuid,uuid,integer,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.save_film_operation(uuid,uuid,integer,jsonb,jsonb) to service_role;

create or replace function public.undo_film_operation(p_user_id uuid,p_project_id uuid)
returns text language plpgsql security definer set search_path='' as $$
declare f public.films; o public.film_operations;
begin
 perform 1 from public.projects where id=p_project_id and user_id=p_user_id for update;
 if not found then raise exception 'project_not_found'; end if;
 select * into f from public.films where project_id=p_project_id order by version desc limit 1 for update;
 select * into o from public.film_operations where film_id=f.id and undone_at is null order by applied_at desc,id desc limit 1 for update;
 if o.id is null then raise exception 'Aucune opération à annuler sur cette version.'; end if;
 update public.films set data=o.snapshot_before,rev=rev+1 where id=f.id;
 update public.film_operations set undone_at=now() where id=o.id;
 update public.projects set title=coalesce(o.snapshot_before->'info'->>'title',title),type=coalesce(o.snapshot_before->'info'->>'type',type),updated_at=now() where id=p_project_id;
 return o.op->>'name';
end $$;
revoke all on function public.undo_film_operation(uuid,uuid) from public,anon,authenticated;
grant execute on function public.undo_film_operation(uuid,uuid) to service_role;

create or replace function public.queue_render(p_user_id uuid,p_project_id uuid) returns uuid
language plpgsql security definer set search_path='' as $$
declare f public.films; j uuid; v integer;
begin
 perform 1 from public.projects where id=p_project_id and user_id=p_user_id for update;
 if not found then raise exception 'project_not_found'; end if;
 -- Repeated taps/request retries reuse the active job.
 select id into j from public.render_jobs where project_id=p_project_id and status in ('queued','running') order by created_at desc limit 1;
 if j is not null then return j; end if;
 select * into f from public.films where project_id=p_project_id order by version desc limit 1 for update;
 if f.id is null then raise exception 'film_not_found'; end if;
 if not exists(select 1 from jsonb_array_elements(f.data->'scenes') s cross join lateral jsonb_array_elements(s->'shots') sh) then raise exception 'Le film ne contient aucun plan.'; end if;
 if (select coalesce(sum((s->>'durationSec')::numeric),0) from jsonb_array_elements(f.data->'scenes') s) > 600 then raise exception 'La durée maximale actuelle est de 10 minutes.'; end if;
 if f.data->'render'->>'resolution'='4k' then raise exception 'Le moteur accepte actuellement 720p ou 1080p.'; end if;
 v:=f.version;
 if f.rev=0 and f.version>1 then v:=f.version-1;
 else insert into public.films(project_id,user_id,version,data) values(p_project_id,p_user_id,f.version+1,f.data); end if;
 insert into public.render_jobs(project_id,user_id,film_version) values(p_project_id,p_user_id,v) returning id into j;
 return j;
end $$;
revoke all on function public.queue_render(uuid,uuid) from public,anon,authenticated;
grant execute on function public.queue_render(uuid,uuid) to service_role;

create or replace function public.cancel_render(p_job_id uuid) returns boolean
language plpgsql security definer set search_path='' as $$
begin
 update public.render_jobs set status='canceled',finished_at=now(),updated_at=now() where id=p_job_id and user_id=auth.uid() and status in ('queued','running');
 return found;
end $$;
revoke all on function public.cancel_render(uuid) from public,anon;
grant execute on function public.cancel_render(uuid) to authenticated;

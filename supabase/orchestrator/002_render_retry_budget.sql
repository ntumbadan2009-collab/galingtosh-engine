-- Prevent unbounded retry loops after graceful shutdowns/restarts.
begin;
create or replace function public.claim_render_job(p_worker_id text)
returns setof public.render_jobs
language plpgsql security definer set search_path='' as $$
begin
 update public.render_jobs set status='failed',error='retry_budget_exhausted',finished_at=now(),worker_id=null,updated_at=now()
 where status='queued' and attempts>=3;
 return query update public.render_jobs j set status='running',worker_id=p_worker_id,progress=0,attempts=j.attempts+1,updated_at=now()
 where j.id=(select id from public.render_jobs where status='queued' and attempts<3 order by created_at for update skip locked limit 1)
 returning j.*;
end;
$$;
revoke execute on function public.claim_render_job(text) from public,anon,authenticated;
grant execute on function public.claim_render_job(text) to service_role;
commit;

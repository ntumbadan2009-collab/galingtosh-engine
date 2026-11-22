-- Run only in an isolated database, or inside an explicit transaction rolled back by the caller.
do $$
declare uid uuid; pid uuid; cid uuid; mid uuid; token uuid; step integer; st text;
begin
 if has_function_privilege('authenticated','public.claim_production()','execute') then raise exception 'Client can claim'; end if;
 if has_table_privilege('authenticated','public.production_missions','UPDATE') then raise exception 'Client can update missions'; end if;
 select id into uid from auth.users limit 1;
 if uid is null then raise exception 'A test user is required'; end if;
 insert into public.projects(user_id,title,type) values(uid,'__orchestration_test__','custom') returning id into pid;
 insert into public.conversations(user_id,project_id,title) values(uid,pid,'__orchestration_test__') returning id into cid;
 insert into public.production_missions(user_id,project_id,conversation_id,request_id,goal,plan,target_seconds)
 values(uid,pid,cid,gen_random_uuid(),'Test','Test plan',150) returning id into mid;
 if exists(select 1 from public.claim_production() where id=mid) then raise exception 'Unapproved mission claimed'; end if;
 perform public.approve_production(mid,uid);
 perform public.approve_production(mid,uid);
 select lease_token into token from public.claim_production() where id=mid;
 if token is null then raise exception 'Approved mission not claimed'; end if;
 if exists(select 1 from public.claim_production() where id=mid) then raise exception 'Duplicate lease'; end if;
 begin
  perform public.begin_production_step(mid,gen_random_uuid(),'invalid lease');
  raise exception 'Invalid lease accepted' using errcode='P9999';
 exception when sqlstate 'P0001' then null;
 end;
 step:=public.begin_production_step(mid,token,'test_step');
 perform public.finish_production_step(mid,token,step,true,'{"ok":true}'::jsonb,null);
 select status into st from public.production_missions where id=mid;
 if st<>'queued' then raise exception 'Checkpoint did not release the mission'; end if;
 update public.production_missions set available_at=now() where id=mid;
 select lease_token into token from public.claim_production() where id=mid;
 if token is null then raise exception 'Checkpoint not resumed'; end if;
 step:=public.begin_production_step(mid,token,'interrupted_mutation');
 update public.production_missions set lease_until=now()-interval '1 second' where id=mid;
 perform public.claim_production();
 select status into st from public.production_missions where id=mid;
 if st<>'needs_review' then raise exception 'Ambiguous mutation replayed'; end if;
 if not exists(select 1 from public.production_tasks where mission_id=mid and step_no=step and status='uncertain') then raise exception 'Uncertain task not recorded'; end if;
 raise notice 'orchestration SQL tests pass';
end $$;

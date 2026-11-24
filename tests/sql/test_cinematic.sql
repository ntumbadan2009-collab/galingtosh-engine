begin;
do $$
declare uid uuid:=gen_random_uuid(); pid uuid; cid uuid; mid uuid; old_job uuid; new_job uuid; lease uuid:=gen_random_uuid(); state jsonb;
 original jsonb:='{"info":{"editorialLevel":5,"visualPolicy":"strict","title":"Test","type":"custom"},"render":{"resolution":"720p"},"scenes":[{"id":"s","durationSec":4,"narration":{"text":"Une démonstration claire."},"shots":[{"id":"a","visualMode":"programmatic","visualText":"Une démonstration claire.","visualSpec":{"type":"focus","items":[{"text":"Une démonstration claire."}]},"inSec":0,"outSec":2},{"id":"b","visualMode":"programmatic","visualText":"Une démonstration claire.","inSec":2,"outSec":4}]}]}'::jsonb;
begin
 if has_function_privilege('authenticated','public.retry_cinematic_repair(uuid,uuid,uuid,text[])','execute') then raise exception 'Unauthorized repair grant'; end if;
 insert into auth.users values(uid);
 insert into public.projects(user_id,title,type) values(uid,'Test','custom') returning id into pid;
 insert into public.conversations(user_id,project_id,title) values(uid,pid,'Test') returning id into cid;
 insert into public.films(project_id,user_id,version,data) values(pid,uid,1,original),(pid,uid,2,original);
 insert into public.render_jobs(project_id,user_id,film_version,status,output_path,technical_report) values(pid,uid,1,'done','old.mp4','{"editorial_level":5,"duration_seconds":4,"width":1280,"height":720,"editorial_quality":{"passed":true},"cinematic_review":{"sampling":"two_final_frames_per_shot","batches":[{"index":0,"count":2}]}}') returning id into old_job;
 insert into storage.objects values('renders','old.mp4');
 insert into public.production_missions(user_id,project_id,conversation_id,request_id,goal,plan,target_seconds,status,approved_at,lease_token,lease_until,render_job_id)
 values(uid,pid,cid,gen_random_uuid(),'test','test',4,'waiting_render',now(),lease,now()+interval '5 minutes',old_job) returning id into mid;
 -- Without review, the database must refuse completion even with valid output metadata.
 begin
  perform public.release_production(mid,lease,'done',null,2);
  raise exception 'Ungated delivery' using errcode='P9999';
 exception when sqlstate 'P0001' then null;
 end;
 insert into public.quality_reports(mission_id,render_job_id,check_name,passed,evidence)
 values(mid,old_job,'level4_visual_000',false,'{"sampling":"two_final_frames_per_shot","verdict":[{"shotId":"a","relevance":"pass","readability":"fail","composition":"pass"},{"shotId":"b","relevance":"pass","readability":"pass","composition":"pass"}]}');
 -- A changed draft cannot be overwritten, even if its current JSON happens to match.
 update public.films set rev=1 where project_id=pid and version=2;
 if public.retry_cinematic_repair(mid,lease,old_job,array['a']) is not null then raise exception 'Concurrent draft overwritten';end if;
 update public.films set rev=0 where project_id=pid and version=2;
 if public.retry_cinematic_repair(mid,lease,old_job,array['b']) is not null then raise exception 'Unrejected shot repaired';end if;
 new_job:=public.retry_cinematic_repair(mid,lease,old_job,array['a']);
 if new_job is null or new_job=old_job then raise exception 'Repair did not queue';end if;
 select data into state from public.films where project_id=pid and version=2;
 if (state#>'{scenes,0,shots,0}')?'visualSpec' then raise exception 'Repair did not change target';end if;
 if state#>'{scenes,0,shots,1}' is distinct from original#>'{scenes,0,shots,1}' then raise exception 'Unrelated plan changed';end if;
 if (select data from public.films where project_id=pid and version=1) is distinct from original then raise exception 'Old snapshot changed';end if;
 lease:=gen_random_uuid();
 update public.production_missions set lease_token=lease,lease_until=now()+interval '5 minutes' where id=mid;
 update public.render_jobs set status='done',output_path='new.mp4',technical_report=(select technical_report from public.render_jobs where id=old_job) where id=new_job;
 insert into storage.objects values('renders','new.mp4');
 if public.retry_cinematic_repair(mid,lease,new_job,array['a']) is not null then raise exception 'Retry budget bypass';end if;
 insert into public.quality_reports(mission_id,render_job_id,check_name,passed,evidence)
 values(mid,new_job,'level4_visual_000',true,'{"sampling":"two_final_frames_per_shot","verdict":[{"shotId":"a","relevance":"pass","readability":"pass","composition":"pass"},{"shotId":"b","relevance":"pass","readability":"pass","composition":"pass"}]}');
 perform public.release_production(mid,lease,'done',null,2);
 if (select status from public.production_missions where id=mid)<>'done' then raise exception 'Validated delivery refused';end if;
 raise notice 'Cinematic transaction and gate tests passed';
end $$;
rollback;

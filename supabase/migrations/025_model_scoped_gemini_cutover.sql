-- Retain old model cooldown history without blocking other models on the key.
insert into public.gemini_api_cooldowns(api_key_scope,blocked_until,reason)
select api_key_scope||':gemini-3.5-flash',blocked_until,reason
from public.gemini_api_cooldowns where position(':' in api_key_scope)=0
on conflict(api_key_scope) do update set blocked_until=greatest(gemini_api_cooldowns.blocked_until,excluded.blocked_until);
update public.gemini_api_cooldowns set blocked_until=least(blocked_until,now()) where position(':' in api_key_scope)=0;

create function public.reserve_gemini_model_slot(p_api_key_scope text,p_model_id text,p_limit integer,p_window_seconds integer,p_queue_id uuid)
returns table(allowed boolean,wait_seconds integer)
language plpgsql security definer set search_path=public as $$
declare v_until timestamptz;
begin
  perform pg_advisory_xact_lock(hashtext(p_api_key_scope));
  select c.blocked_until into v_until from public.gemini_api_cooldowns c where c.api_key_scope=p_api_key_scope||':'||p_model_id;
  if v_until>now() then
    return query select false,greatest(1,ceil(extract(epoch from(v_until-now())))::integer);
    return;
  end if;
  -- The ten-RPM budget remains shared across every model using this key.
  return query select * from public.reserve_gemini_api_slot(p_api_key_scope,p_limit,p_window_seconds,p_queue_id);
end;
$$;
revoke all on function public.reserve_gemini_model_slot(text,text,integer,integer,uuid) from public,anon,authenticated;
grant execute on function public.reserve_gemini_model_slot(text,text,integer,integer,uuid) to service_role;

create function public.matching_provider_status(p_model_id text)
returns table(blocked_until timestamptz,reason text)
language sql security definer set search_path=public as $$
  select c.blocked_until,c.reason from public.gemini_api_cooldowns c
  where c.blocked_until>now() and right(c.api_key_scope,length(p_model_id)+1)=':'||p_model_id
  order by c.blocked_until desc limit 1;
$$;
revoke all on function public.matching_provider_status(text) from public,anon;
grant execute on function public.matching_provider_status(text) to authenticated,service_role;

alter table public.gemini_analysis_queue drop constraint gemini_analysis_queue_status_check;
alter table public.gemini_analysis_queue add constraint gemini_analysis_queue_status_check
  check(status in ('pending','processing','completed','failed','superseded'));

create function public.claim_gemini_analysis_tasks(p_limit integer,p_worker_id text,p_model_id text)
returns setof public.gemini_analysis_queue
language plpgsql security definer set search_path=public as $$
begin
  return query with candidates as (
    select q.id from public.gemini_analysis_queue q join public.jobs j on j.id=q.job_id
    where q.model_id=p_model_id and ((q.status='pending' and q.next_attempt_at<=now())
      or (q.status='processing' and q.processing_started_at<now()-interval '10 minutes'))
    order by j.first_seen_at desc,q.created_at,q.id
    for update of q skip locked limit greatest(1,least(p_limit,20))
  ) update public.gemini_analysis_queue q set status='processing',processing_started_at=now(),worker_id=p_worker_id,updated_at=now()
    from candidates c where q.id=c.id returning q.*;
end;
$$;
revoke all on function public.claim_gemini_analysis_tasks(integer,text,text) from public,anon,authenticated;
grant execute on function public.claim_gemini_analysis_tasks(integer,text,text) to service_role;

create function public.migrate_pending_matching_model(p_old_model text,p_new_model text)
returns integer language plpgsql security definer set search_path=public as $$
declare r record; new_id uuid; migrated integer:=0; v_hash text;
begin
  if p_old_model=p_new_model then return 0; end if;
  for r in select q.*,c.content_hash,j.description
    from public.gemini_analysis_queue q
    join public.cv_documents c on c.id=q.cv_document_id and c.user_id=q.user_id and c.is_active
    join public.jobs j on j.id=q.job_id and j.is_active
    where q.model_id=p_old_model and q.status='pending' and length(btrim(j.description))>=240
    for update of q skip locked
  loop
    v_hash:=md5(jsonb_build_object('cv',r.content_hash,'job',r.job_id,'description',r.description,'model',p_new_model,'rubric',r.rubric_version)::text);
    new_id:=public.enqueue_gemini_analysis_atomic(r.user_id,r.job_id,r.cv_document_id,p_new_model,r.rubric_version,v_hash);
    update public.gemini_analysis_queue set status='superseded',last_error='Moved to '||p_new_model||' (task '||new_id::text||')',updated_at=now() where id=r.id;
    migrated:=migrated+1;
  end loop;
  return migrated;
end;
$$;
revoke all on function public.migrate_pending_matching_model(text,text) from public,anon,authenticated;
grant execute on function public.migrate_pending_matching_model(text,text) to service_role;

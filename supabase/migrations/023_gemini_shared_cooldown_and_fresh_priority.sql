create table public.gemini_api_cooldowns (
  api_key_scope text primary key,
  blocked_until timestamptz not null,
  reason text not null
);
alter table public.gemini_api_cooldowns enable row level security;

create function public.defer_gemini_api_key(p_api_key_scope text, p_blocked_until timestamptz, p_reason text)
returns void language sql security definer set search_path=public as $$
  insert into public.gemini_api_cooldowns values(p_api_key_scope,p_blocked_until,left(p_reason,1000))
  on conflict(api_key_scope) do update set
    blocked_until=greatest(gemini_api_cooldowns.blocked_until,excluded.blocked_until), reason=excluded.reason;
$$;
revoke all on function public.defer_gemini_api_key(text,timestamptz,text) from public,anon,authenticated;
grant execute on function public.defer_gemini_api_key(text,timestamptz,text) to service_role;

create function public.matching_provider_status()
returns table(blocked_until timestamptz,reason text)
language sql security definer set search_path=public as $$
  select c.blocked_until,c.reason from public.gemini_api_cooldowns c
  where c.blocked_until>now() order by c.blocked_until desc limit 1;
$$;
revoke all on function public.matching_provider_status() from public,anon;
grant execute on function public.matching_provider_status() to authenticated,service_role;

create or replace function public.reserve_gemini_api_slot(
  p_api_key_scope text,p_limit integer,p_window_seconds integer,p_queue_id uuid
)
returns table(allowed boolean,wait_seconds integer)
language plpgsql security definer set search_path=public as $$
declare
  v_count integer;
  v_oldest timestamptz;
  v_until timestamptz;
  v_window integer:=greatest(p_window_seconds,60);
begin
  perform pg_advisory_xact_lock(hashtext(p_api_key_scope));
  select c.blocked_until into v_until from public.gemini_api_cooldowns c where c.api_key_scope=p_api_key_scope;
  if v_until>now() then
    return query select false,greatest(1,ceil(extract(epoch from(v_until-now())))::integer);
    return;
  end if;
  select count(*)::integer,min(attempted_at) into v_count,v_oldest
    from public.gemini_api_attempts where api_key_scope=p_api_key_scope
    and attempted_at>=now()-make_interval(secs=>v_window);
  if v_count>=greatest(1,least(p_limit,10)) then
    return query select false,greatest(1,ceil(extract(epoch from(v_oldest+make_interval(secs=>v_window)-now())))::integer);
    return;
  end if;
  insert into public.gemini_api_attempts(api_key_scope,queue_id) values(p_api_key_scope,p_queue_id);
  update public.gemini_analysis_queue set attempts=attempts+1,updated_at=now() where id=p_queue_id;
  return query select true,0;
end;
$$;
revoke all on function public.reserve_gemini_api_slot(text,integer,integer,uuid) from public,anon,authenticated;
grant execute on function public.reserve_gemini_api_slot(text,integer,integer,uuid) to service_role;

create or replace function public.claim_gemini_analysis_tasks(p_limit integer,p_worker_id text)
returns setof public.gemini_analysis_queue
language plpgsql security definer set search_path=public as $$
begin
  return query with candidates as (
    select q.id from public.gemini_analysis_queue q join public.jobs j on j.id=q.job_id
    where (q.status='pending' and q.next_attempt_at<=now())
       or (q.status='processing' and q.processing_started_at<now()-interval '10 minutes')
    order by j.first_seen_at desc,q.created_at,q.id
    for update of q skip locked limit greatest(1,least(p_limit,20))
  ) update public.gemini_analysis_queue q set status='processing',processing_started_at=now(),worker_id=p_worker_id,updated_at=now()
    from candidates c where q.id=c.id returning q.*;
end;
$$;
revoke all on function public.claim_gemini_analysis_tasks(integer,text) from public,anon,authenticated;
grant execute on function public.claim_gemini_analysis_tasks(integer,text) to service_role;

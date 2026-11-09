-- Conservative app-wide quota, across keys/models, including retries.
-- Keep the attempt ledger and queued tasks; never reset either at deployment.
create or replace function public.reserve_gemini_api_slot(
  p_api_key_scope text,p_limit integer,p_window_seconds integer,p_queue_id uuid
)
returns table(allowed boolean,wait_seconds integer)
language plpgsql security definer set search_path=public as $$
declare
  v_count integer; v_oldest timestamptz; v_until timestamptz;
  v_window integer:=greatest(p_window_seconds,60);
  v_day timestamptz:=date_trunc('day',now() at time zone 'America/Los_Angeles') at time zone 'America/Los_Angeles';
  v_next_day timestamptz:=(date_trunc('day',now() at time zone 'America/Los_Angeles')+interval '1 day') at time zone 'America/Los_Angeles';
  v_wait integer:=0;
begin
  -- One lock across keys: rotating credentials does not reset the daily budget.
  perform pg_advisory_xact_lock(hashtext('ats-gemini-daily-budget'));
  perform pg_advisory_xact_lock(hashtext(p_api_key_scope));
  if p_api_key_scope<>'local-mock' then
    select count(*) into v_count from public.gemini_api_attempts
      where api_key_scope<>'local-mock' and attempted_at>now()-interval '24 hours';
    if v_count>=450 then
      select attempted_at into v_oldest from public.gemini_api_attempts
        where api_key_scope<>'local-mock' and attempted_at>now()-interval '24 hours'
        order by attempted_at offset (v_count-450) limit 1;
      v_wait:=greatest(1,ceil(extract(epoch from(v_oldest+interval '24 hours'-now())))::integer);
    end if;
    select count(*) into v_count from public.gemini_api_attempts
      where api_key_scope<>'local-mock' and attempted_at>=v_day;
    if v_count>=450 then
      v_wait:=greatest(v_wait,ceil(extract(epoch from(v_next_day-now())))::integer);
    end if;
    if v_wait>0 then return query select false,v_wait; return; end if;
  end if;
  select c.blocked_until into v_until from public.gemini_api_cooldowns c where c.api_key_scope=p_api_key_scope;
  if v_until>now() then
    return query select false,greatest(1,ceil(extract(epoch from(v_until-now())))::integer); return;
  end if;
  select count(*),min(attempted_at) into v_count,v_oldest from public.gemini_api_attempts
    where api_key_scope=p_api_key_scope and attempted_at>now()-make_interval(secs=>v_window);
  if v_count>=greatest(1,least(p_limit,10)) then
    return query select false,greatest(1,ceil(extract(epoch from(v_oldest+make_interval(secs=>v_window)-now())))::integer); return;
  end if;
  insert into public.gemini_api_attempts(api_key_scope,queue_id) values(p_api_key_scope,p_queue_id);
  update public.gemini_analysis_queue set attempts=attempts+1,updated_at=now() where id=p_queue_id;
  return query select true,0;
end;
$$;
revoke all on function public.reserve_gemini_api_slot(text,integer,integer,uuid) from public,anon,authenticated;
grant execute on function public.reserve_gemini_api_slot(text,integer,integer,uuid) to service_role;

-- Keep lock acquisition order consistent between direct and model reservations.
create or replace function public.reserve_gemini_model_slot(p_api_key_scope text,p_model_id text,p_limit integer,p_window_seconds integer,p_queue_id uuid)
returns table(allowed boolean,wait_seconds integer)
language plpgsql security definer set search_path=public as $$
declare v_until timestamptz;
begin
  perform pg_advisory_xact_lock(hashtext('ats-gemini-daily-budget'));
  perform pg_advisory_xact_lock(hashtext(p_api_key_scope));
  select c.blocked_until into v_until from public.gemini_api_cooldowns c where c.api_key_scope=p_api_key_scope||':'||p_model_id;
  if v_until>now() then
    return query select false,greatest(1,ceil(extract(epoch from(v_until-now())))::integer); return;
  end if;
  return query select * from public.reserve_gemini_api_slot(p_api_key_scope,p_limit,p_window_seconds,p_queue_id);
end;
$$;
revoke all on function public.reserve_gemini_model_slot(text,text,integer,integer,uuid) from public,anon,authenticated;
grant execute on function public.reserve_gemini_model_slot(text,text,integer,integer,uuid) to service_role;

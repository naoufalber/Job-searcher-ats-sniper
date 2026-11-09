-- Lower the global key-scoped ceiling without removing queued work/history.
create or replace function public.reserve_gemini_api_slot(
  p_api_key_scope text, p_limit integer, p_window_seconds integer, p_queue_id uuid
)
returns table (allowed boolean, wait_seconds integer)
language plpgsql security definer set search_path = public
as $$
declare
  v_count integer;
  v_oldest timestamptz;
  v_window integer := greatest(p_window_seconds, 60);
begin
  perform pg_advisory_xact_lock(hashtext(p_api_key_scope));
  select count(*)::integer, min(attempted_at) into v_count, v_oldest
    from public.gemini_api_attempts
   where api_key_scope = p_api_key_scope
     and attempted_at >= now() - make_interval(secs => v_window);
  if v_count >= greatest(1, least(p_limit, 10)) then
    return query select false, greatest(1, ceil(extract(epoch from
      (v_oldest + make_interval(secs => v_window) - now())))::integer);
    return;
  end if;
  insert into public.gemini_api_attempts(api_key_scope, queue_id) values(p_api_key_scope, p_queue_id);
  update public.gemini_analysis_queue set attempts = attempts + 1, updated_at = now() where id = p_queue_id;
  return query select true, 0;
end;
$$;
revoke all on function public.reserve_gemini_api_slot(text, integer, integer, uuid) from public, anon, authenticated;
grant execute on function public.reserve_gemini_api_slot(text, integer, integer, uuid) to service_role;

-- Release only the former daily-cap deferrals. Preserve HTTP/network backoff,
-- failures, completed results, processing leases, and all attempt counters.
update public.gemini_analysis_queue set next_attempt_at = now(), updated_at = now()
where status = 'pending' and attempts = 0 and last_error is null
  and next_attempt_at > now() + interval '1 hour';

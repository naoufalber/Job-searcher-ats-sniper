create table if not exists public.gemini_analysis_queue (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  cv_document_id uuid not null references public.cv_documents(id) on delete cascade,
  model_id text not null,
  rubric_version text not null,
  input_hash text not null,
  status text not null default 'pending' check (status in ('pending', 'processing', 'completed', 'failed')),
  attempts integer not null default 0 check (attempts >= 0),
  next_attempt_at timestamptz not null default now(),
  processing_started_at timestamptz,
  worker_id text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, job_id, cv_document_id, model_id, rubric_version, input_hash)
);
create index if not exists gemini_queue_claim_idx on public.gemini_analysis_queue (status, next_attempt_at, created_at);
create index if not exists gemini_queue_user_idx on public.gemini_analysis_queue (user_id, created_at desc);

create table if not exists public.gemini_api_attempts (
  id bigint generated always as identity primary key,
  api_key_scope text not null,
  queue_id uuid not null references public.gemini_analysis_queue(id) on delete cascade,
  attempted_at timestamptz not null default now()
);
create index if not exists gemini_attempts_window_idx on public.gemini_api_attempts (api_key_scope, attempted_at desc);

alter table public.gemini_analysis_queue enable row level security;
create policy "users read own gemini queue" on public.gemini_analysis_queue
  for select using (auth.uid() = user_id);
create policy "users create own gemini queue" on public.gemini_analysis_queue
  for insert with check (auth.uid() = user_id);

create or replace function public.claim_gemini_analysis_tasks(p_limit integer, p_worker_id text)
returns setof public.gemini_analysis_queue
language plpgsql security definer set search_path = public
as $$
begin
  return query
  with candidates as (
    select q.id
    from public.gemini_analysis_queue q
    where (q.status = 'pending' and q.next_attempt_at <= now())
       or (q.status = 'processing' and q.processing_started_at < now() - interval '10 minutes')
    order by q.next_attempt_at, q.created_at
    for update skip locked
    limit greatest(1, least(p_limit, 20))
  )
  update public.gemini_analysis_queue q
     set status = 'processing', processing_started_at = now(), worker_id = p_worker_id, updated_at = now()
    from candidates c
   where q.id = c.id
  returning q.*;
end;
$$;

create or replace function public.reserve_gemini_api_slot(
  p_api_key_scope text, p_limit integer, p_window_seconds integer, p_queue_id uuid
)
returns table (allowed boolean, wait_seconds integer)
language plpgsql security definer set search_path = public
as $$
declare
  v_count integer;
  v_oldest timestamptz;
  v_wait integer;
begin
  perform pg_advisory_xact_lock(hashtext(p_api_key_scope));
  delete from public.gemini_api_attempts where attempted_at < now() - make_interval(secs => greatest(p_window_seconds, 1));
  select count(*)::integer, min(attempted_at) into v_count, v_oldest
    from public.gemini_api_attempts
   where api_key_scope = p_api_key_scope
     and attempted_at >= now() - make_interval(secs => greatest(p_window_seconds, 1));
  if v_count >= greatest(p_limit, 1) then
    v_wait := greatest(1, ceil(extract(epoch from (v_oldest + make_interval(secs => greatest(p_window_seconds, 1)) - now())))::integer);
    return query select false, v_wait;
    return;
  end if;
  insert into public.gemini_api_attempts(api_key_scope, queue_id) values (p_api_key_scope, p_queue_id);
  update public.gemini_analysis_queue set attempts = attempts + 1, updated_at = now() where id = p_queue_id;
  return query select true, 0;
end;
$$;

revoke all on function public.claim_gemini_analysis_tasks(integer, text) from public;
revoke all on function public.reserve_gemini_api_slot(text, integer, integer, uuid) from public;
grant execute on function public.claim_gemini_analysis_tasks(integer, text) to service_role;
grant execute on function public.reserve_gemini_api_slot(text, integer, integer, uuid) to service_role;

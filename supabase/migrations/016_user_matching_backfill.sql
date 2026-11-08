create table if not exists public.matching_backfill_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  preferences_updated_at timestamptz not null,
  status text not null default 'pending' check (status in ('pending', 'processing', 'completed', 'failed')),
  jobs_considered integer not null default 0,
  tasks_queued integer not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  unique (user_id, preferences_updated_at)
);

create index if not exists matching_backfill_due_idx
  on public.matching_backfill_requests (status, created_at);

alter table public.matching_backfill_requests enable row level security;
create policy "users read own matching backfills" on public.matching_backfill_requests
  for select to authenticated using (auth.uid() = user_id);

create or replace function public.enqueue_matching_for_job(
  p_job_id uuid, p_model_id text, p_rubric_version text
)
returns integer
language plpgsql security definer set search_path = public
as $$
declare
  v_job public.jobs%rowtype;
  v_user record;
  v_count integer := 0;
  v_hash text;
begin
  select * into v_job from public.jobs where id = p_job_id;
  if v_job.id is null or v_job.description is null or length(btrim(v_job.description)) < 240 then
    return 0;
  end if;

  for v_user in
    select p.user_id, c.id as cv_document_id, c.content_hash
    from public.user_preferences p
    join public.cv_documents c on c.user_id = p.user_id and c.is_active = true
    where p.onboarding_completed_at is not null
      and (cardinality(p.target_roles) = 0 or exists (
        select 1 from unnest(p.target_roles) role where v_job.title ilike '%' || role || '%'
      ))
      and (cardinality(p.target_locations) = 0 or v_job.location is null or exists (
        select 1 from unnest(p.target_locations) location where v_job.location ilike '%' || location || '%'
      ))
  loop
    v_hash := md5(jsonb_build_object('cv', v_user.content_hash, 'job', p_job_id, 'description', v_job.description, 'model', p_model_id, 'rubric', p_rubric_version)::text);
    perform public.enqueue_gemini_analysis_atomic(v_user.user_id, p_job_id, v_user.cv_document_id, p_model_id, p_rubric_version, v_hash);
    v_count := v_count + 1;
  end loop;
  return v_count;
end;
$$;

revoke all on function public.enqueue_matching_for_job(uuid, text, text) from public;
grant execute on function public.enqueue_matching_for_job(uuid, text, text) to service_role;

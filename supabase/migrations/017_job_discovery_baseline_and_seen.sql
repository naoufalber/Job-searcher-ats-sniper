-- One-time staging baseline. Existing rows are snapshotted once; later deployments
-- must not recreate or refresh this baseline.
alter table public.jobs
  add column if not exists is_new_since_baseline boolean not null default false;

create table if not exists public.job_discovery_baseline (
  id integer primary key check (id = 1),
  captured_at timestamptz not null default now(),
  reason text not null default 'staging activation baseline'
);

create table if not exists public.job_discovery_baseline_jobs (
  job_id uuid primary key references public.jobs(id) on delete cascade,
  captured_at timestamptz not null default now()
);

insert into public.job_discovery_baseline (id)
values (1)
on conflict (id) do nothing;

insert into public.job_discovery_baseline_jobs (job_id)
select id from public.jobs
on conflict (job_id) do nothing;

alter table public.job_discovery_baseline enable row level security;
alter table public.job_discovery_baseline_jobs enable row level security;

drop policy if exists "authenticated users read discovery baseline" on public.job_discovery_baseline;
create policy "authenticated users read discovery baseline"
  on public.job_discovery_baseline for select to authenticated using (true);

drop policy if exists "authenticated users read baseline jobs" on public.job_discovery_baseline_jobs;
create policy "authenticated users read baseline jobs"
  on public.job_discovery_baseline_jobs for select to authenticated using (true);

create table if not exists public.user_job_seen (
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  seen_at timestamptz not null default now(),
  primary key (user_id, job_id)
);

create index if not exists user_job_seen_job_idx on public.user_job_seen (job_id);
alter table public.user_job_seen enable row level security;

drop policy if exists "users read own seen jobs" on public.user_job_seen;
create policy "users read own seen jobs"
  on public.user_job_seen for select to authenticated using (auth.uid() = user_id);

drop policy if exists "users mark own jobs seen" on public.user_job_seen;
create policy "users mark own jobs seen"
  on public.user_job_seen for insert to authenticated with check (auth.uid() = user_id);

drop policy if exists "users update own seen jobs" on public.user_job_seen;
create policy "users update own seen jobs"
  on public.user_job_seen for update to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

create or replace function public.ingest_job_atomic(
  p_source text,
  p_external_job_id text,
  p_company_name text,
  p_title text,
  p_location text,
  p_country text,
  p_contract_type text,
  p_remote_type text,
  p_canonical_url text,
  p_description text,
  p_first_seen_at timestamptz,
  p_publication_date timestamptz,
  p_metadata jsonb
)
returns table (result_job_id uuid, result_source_id bigint)
language plpgsql security definer
set search_path = public
as $$
declare
  v_source_id bigint;
  v_job_id uuid;
  v_url_job_id uuid;
  v_is_new boolean;
begin
  insert into public.sources (name, kind, base_url)
  values (p_source, 'collector', split_part(p_canonical_url, '/', 1) || '//' || split_part(p_canonical_url, '/', 3))
  on conflict (name) do update set kind = excluded.kind, base_url = excluded.base_url
  returning id into v_source_id;

  select id into v_source_id from public.sources where name = p_source for update;
  select js.job_id into v_job_id from public.job_sources js
    where js.source_id = v_source_id and js.external_job_id = p_external_job_id for update;
  select j.id into v_url_job_id from public.jobs j
    where j.canonical_url = p_canonical_url for update;
  if v_job_id is null then v_job_id := v_url_job_id; end if;

  if v_job_id is null then
    v_is_new := exists (select 1 from public.job_discovery_baseline where id = 1);
    insert into public.jobs (
      canonical_url, company_name, title, location, country, contract_type,
      description, remote_type, first_seen_at, publication_date, last_seen_at,
      metadata, is_active, is_new_since_baseline
    ) values (
      p_canonical_url, p_company_name, p_title, p_location, p_country,
      p_contract_type, p_description, p_remote_type,
      coalesce(p_first_seen_at, now()), p_publication_date, now(),
      coalesce(p_metadata, '{}'::jsonb), true, v_is_new
    ) on conflict (canonical_url) do update set last_seen_at = excluded.last_seen_at
    returning id into v_job_id;
  else
    update public.jobs set
      canonical_url = case when not exists (
        select 1 from public.jobs other where other.canonical_url = p_canonical_url and other.id <> v_job_id
      ) then p_canonical_url else canonical_url end,
      company_name = p_company_name, title = p_title, location = p_location,
      country = p_country, contract_type = p_contract_type, description = p_description,
      remote_type = p_remote_type, publication_date = p_publication_date,
      last_seen_at = now(),
      metadata = case when metadata->>'import_kind' = 'historical_sqlite'
        then metadata || coalesce(p_metadata, '{}'::jsonb) || jsonb_build_object('import_kind', 'historical_sqlite')
        else coalesce(p_metadata, '{}'::jsonb) end,
      is_active = true
    where id = v_job_id;
  end if;

  insert into public.job_sources (job_id, source_id, external_job_id, source_url, last_seen_at)
  values (v_job_id, v_source_id, p_external_job_id, p_canonical_url, now())
  on conflict (source_id, external_job_id) do update set
    job_id = excluded.job_id, source_url = excluded.source_url, last_seen_at = excluded.last_seen_at;

  return query select v_job_id, v_source_id;
end;
$$;

revoke execute on function public.ingest_job_atomic(
  text, text, text, text, text, text, text, text, text, text, timestamptz,
  timestamptz, jsonb
) from public;
grant execute on function public.ingest_job_atomic(
  text, text, text, text, text, text, text, text, text, text, timestamptz,
  timestamptz, jsonb
) to service_role;

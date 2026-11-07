create extension if not exists pgcrypto;

create table public.sources (
  id bigint generated always as identity primary key,
  name text not null unique,
  kind text not null,
  base_url text,
  created_at timestamptz not null default now()
);

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  canonical_url text not null unique,
  company_name text not null,
  title text not null,
  location text,
  description text,
  experience_level text,
  remote_type text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb
);

create table public.job_sources (
  job_id uuid not null references public.jobs(id) on delete cascade,
  source_id bigint not null references public.sources(id) on delete restrict,
  external_job_id text not null,
  source_company_slug text,
  source_url text not null,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  primary key (source_id, external_job_id)
);

create table public.user_job_status (
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  status text not null default 'new' check (status in ('new', 'saved', 'applied', 'rejected', 'archived')),
  notes text,
  updated_at timestamptz not null default now(),
  primary key (user_id, job_id)
);

create table public.collection_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null check (status in ('running', 'succeeded', 'failed')),
  provider_counts jsonb not null default '{}'::jsonb,
  error_summary text
);

create index jobs_active_last_seen_idx on public.jobs (is_active, last_seen_at desc);
create index jobs_search_idx on public.jobs using gin (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(company_name, '') || ' ' || coalesce(location, '')));
create index job_sources_job_id_idx on public.job_sources (job_id);
create index user_job_status_status_idx on public.user_job_status (user_id, status);

alter table public.sources enable row level security;
alter table public.jobs enable row level security;
alter table public.job_sources enable row level security;
alter table public.user_job_status enable row level security;
alter table public.collection_runs enable row level security;

create policy "active jobs are publicly readable" on public.jobs for select using (is_active = true);
create policy "sources are publicly readable" on public.sources for select using (true);
create policy "job source links are publicly readable" on public.job_sources for select using (true);
create policy "users read their own statuses" on public.user_job_status for select using (auth.uid() = user_id);
create policy "users create their own statuses" on public.user_job_status for insert with check (auth.uid() = user_id);
create policy "users update their own statuses" on public.user_job_status for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "users delete their own statuses" on public.user_job_status for delete using (auth.uid() = user_id);

comment on table public.jobs is 'Global normalized job records; written by a future server-side collector integration.';
comment on table public.user_job_status is 'Per-user saved/application workflow state; never written by the collector.';
comment on table public.collection_runs is 'Operational history for future additive ingestion.';

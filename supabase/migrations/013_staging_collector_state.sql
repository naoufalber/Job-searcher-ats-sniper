create table if not exists public.staging_collector_state (
  source text not null,
  external_job_id text not null,
  job_id uuid references public.jobs(id) on delete set null,
  canonical_url text not null,
  status text not null default 'pending' check (status in ('pending', 'complete', 'needs_description', 'enrichment_pending', 'enrichment_failed')),
  attempts integer not null default 0 check (attempts >= 0),
  next_attempt_at timestamptz,
  last_error text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  primary key (source, external_job_id)
);
create index if not exists staging_collector_state_due_idx on public.staging_collector_state (status, next_attempt_at);
alter table public.staging_collector_state enable row level security;

create or replace function public.record_staging_collector_state(
  p_source text, p_external_job_id text, p_job_id uuid, p_canonical_url text, p_status text
)
returns void
language plpgsql security definer set search_path = public
as $$
begin
  insert into public.staging_collector_state (source, external_job_id, job_id, canonical_url, status)
  values (p_source, p_external_job_id, p_job_id, p_canonical_url, p_status)
  on conflict (source, external_job_id) do update set
    job_id = excluded.job_id,
    canonical_url = excluded.canonical_url,
    status = case
      when public.staging_collector_state.status in ('enrichment_pending', 'enrichment_failed')
        and excluded.status = 'complete' then public.staging_collector_state.status
      else excluded.status
    end,
    last_seen_at = now();
end;
$$;
revoke all on function public.record_staging_collector_state(text, text, uuid, text, text) from public;
grant execute on function public.record_staging_collector_state(text, text, uuid, text, text) to service_role;

-- Keep the shared job catalogue private to authenticated application users.
-- Machine ingestion continues to use service_role and is unaffected.
drop policy if exists "active jobs are publicly readable" on public.jobs;
create policy "authenticated users read active jobs" on public.jobs
  for select to authenticated using (is_active = true);

drop policy if exists "sources are publicly readable" on public.sources;
create policy "authenticated users read sources" on public.sources
  for select to authenticated using (true);

drop policy if exists "job source links are publicly readable" on public.job_sources;
create policy "authenticated users read job source links" on public.job_sources
  for select to authenticated using (true);

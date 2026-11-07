-- Local-only deterministic data. `supabase db reset` reapplies this file.
-- Never run this seed against a hosted project.

insert into public.sources (name, kind, base_url)
values ('local-fixture', 'test', 'https://example.invalid')
on conflict (name) do nothing;

insert into public.jobs (id, canonical_url, company_name, title, location, description, is_active)
values (
  '00000000-0000-4000-8000-000000000001',
  'https://example.invalid/jobs/local-fixture',
  'Local Fixture Co',
  'Data Engineer (local test fixture)',
  'Paris, France',
  'Fixture data used only by local integration tests.',
  true
)
on conflict (id) do update set
  company_name = excluded.company_name,
  title = excluded.title,
  location = excluded.location,
  description = excluded.description,
  is_active = excluded.is_active;

insert into public.job_sources (job_id, source_id, external_job_id, source_url)
select '00000000-0000-4000-8000-000000000001', id, 'local-fixture-1', 'https://example.invalid/jobs/local-fixture'
from public.sources where name = 'local-fixture'
on conflict (source_id, external_job_id) do update set
  job_id = excluded.job_id,
  source_url = excluded.source_url,
  last_seen_at = now();

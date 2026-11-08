alter table public.jobs add column if not exists description_status text not null default 'missing';
alter table public.jobs add column if not exists description_source text;
alter table public.jobs add column if not exists salary_min numeric;
alter table public.jobs add column if not exists salary_max numeric;
alter table public.jobs add column if not exists salary_currency text;
alter table public.jobs add column if not exists required_skills jsonb not null default '[]'::jsonb;
alter table public.jobs add column if not exists recruiter_name text;
alter table public.jobs add column if not exists enrichment_error text;

alter table public.user_job_status add column if not exists application_status text not null default 'to_review';
alter table public.user_job_status add column if not exists applied_at timestamptz;
alter table public.user_job_status add column if not exists cv_document_id uuid;
alter table public.user_job_status add column if not exists recruiter_contact text;
alter table public.user_job_status add column if not exists next_follow_up_at timestamptz;
alter table public.user_job_status add column if not exists interview_at timestamptz;

alter table public.user_job_status drop constraint if exists user_job_status_application_status_check;
alter table public.user_job_status add constraint user_job_status_application_status_check
  check (application_status in ('to_review', 'ready_to_apply', 'applied', 'interview', 'offer', 'rejected', 'withdrawn', 'closed'));

create table if not exists public.cv_documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  storage_path text not null unique,
  original_name text not null,
  mime_type text not null check (mime_type = 'application/pdf'),
  size_bytes integer not null check (size_bytes > 0 and size_bytes <= 5242880),
  content_hash text not null,
  extracted_text text not null,
  is_active boolean not null default false,
  created_at timestamptz not null default now()
);

create unique index if not exists cv_documents_active_user_idx
  on public.cv_documents (user_id) where is_active;
create index if not exists cv_documents_user_idx on public.cv_documents (user_id, created_at desc);

create table if not exists public.job_analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  cv_document_id uuid not null references public.cv_documents(id) on delete cascade,
  model_id text not null,
  rubric_version text not null,
  input_hash text not null,
  status text not null check (status in ('pending', 'completed', 'failed')),
  score integer check (score is null or score between 0 and 100),
  result jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, job_id, cv_document_id, model_id, rubric_version)
);
create index if not exists job_analyses_user_idx on public.job_analyses (user_id, updated_at desc);

alter table public.cv_documents enable row level security;
alter table public.job_analyses enable row level security;

create policy "users manage own cv documents" on public.cv_documents
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "users manage own job analyses" on public.job_analyses
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

insert into storage.buckets (id, name, public)
values ('cv-documents', 'cv-documents', false)
on conflict (id) do nothing;

create policy "users read own cv files" on storage.objects
  for select using (bucket_id = 'cv-documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "users upload own cv files" on storage.objects
  for insert with check (bucket_id = 'cv-documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "users delete own cv files" on storage.objects
  for delete using (bucket_id = 'cv-documents' and (storage.foldername(name))[1] = auth.uid()::text);

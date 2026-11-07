alter table public.jobs add column if not exists country text;
alter table public.jobs add column if not exists contract_type text;
alter table public.jobs add column if not exists publication_date timestamptz;

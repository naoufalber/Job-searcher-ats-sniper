create table if not exists public.user_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  target_roles text[] not null default '{}',
  target_locations text[] not null default '{}',
  employment_types text[] not null default '{}',
  remote_preferences text[] not null default '{}',
  working_languages text[] not null default '{}',
  keywords text[] not null default '{}',
  exclusions text[] not null default '{}',
  min_salary numeric,
  onboarding_completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.user_preferences enable row level security;

drop policy if exists "users read their own preferences" on public.user_preferences;
create policy "users read their own preferences" on public.user_preferences
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists "users insert their own preferences" on public.user_preferences;
create policy "users insert their own preferences" on public.user_preferences
  for insert to authenticated with check (auth.uid() = user_id);

drop policy if exists "users update their own preferences" on public.user_preferences;
create policy "users update their own preferences" on public.user_preferences
  for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

comment on table public.user_preferences is 'Private user-owned discovery preferences and onboarding state.';

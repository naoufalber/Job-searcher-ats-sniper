alter table public.profiles add column if not exists first_name text;
alter table public.profiles add column if not exists last_name text;

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email, first_name, last_name)
  values (
    new.id,
    new.email,
    nullif(trim(new.raw_user_meta_data ->> 'first_name'), ''),
    nullif(trim(new.raw_user_meta_data ->> 'last_name'), '')
  )
  on conflict (id) do update set email = excluded.email, updated_at = now();
  return new;
end;
$$;

comment on column public.profiles.first_name is 'User-provided first name; never used as an identity key.';
comment on column public.profiles.last_name is 'User-provided last name; never used as an identity key.';

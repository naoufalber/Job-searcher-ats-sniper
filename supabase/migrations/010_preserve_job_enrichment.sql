create or replace function public.preserve_non_null_job_fields()
returns trigger
language plpgsql
as $$
begin
  new.description := coalesce(nullif(new.description, ''), old.description);
  new.location := coalesce(nullif(new.location, ''), old.location);
  new.country := coalesce(nullif(new.country, ''), old.country);
  new.contract_type := coalesce(nullif(new.contract_type, ''), old.contract_type);
  new.remote_type := coalesce(nullif(new.remote_type, ''), old.remote_type);
  new.publication_date := coalesce(new.publication_date, old.publication_date);
  return new;
end;
$$;

drop trigger if exists preserve_non_null_job_fields on public.jobs;
create trigger preserve_non_null_job_fields
before update on public.jobs
for each row execute function public.preserve_non_null_job_fields();

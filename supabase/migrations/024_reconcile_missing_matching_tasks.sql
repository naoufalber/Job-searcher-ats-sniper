-- Catch vacancies that arrived before an account completed onboarding or
-- before automatic matching was enabled. Existing work/results are reused.
create function public.enqueue_missing_matching_tasks(p_model_id text,p_rubric_version text,p_limit integer default 25)
returns integer language plpgsql security definer set search_path=public as $$
declare
  j record;
  total integer:=0;
begin
  for j in
    select x.id from public.jobs x where x.is_active
      and length(btrim(x.description))>=240
      and (x.description ~* '(responsabil|mission|qualif|requirement|profile|avantage|benefit|skill)' or regexp_count(x.description,'[.!?]')>=3)
      and exists (
        select 1 from public.user_preferences p join public.cv_documents c on c.user_id=p.user_id and c.is_active
        where p.onboarding_completed_at is not null and length(btrim(c.extracted_text))>0
        and not exists(select 1 from public.job_analyses a where a.user_id=p.user_id and a.job_id=x.id
          and a.cv_document_id=c.id and a.model_id=p_model_id and a.rubric_version=p_rubric_version)
      )
    order by x.first_seen_at desc limit greatest(1,least(p_limit,100))
  loop
    total:=total+public.enqueue_matching_for_job(j.id,p_model_id,p_rubric_version);
  end loop;
  return total;
end;
$$;
revoke all on function public.enqueue_missing_matching_tasks(text,text,integer) from public,anon,authenticated;
grant execute on function public.enqueue_missing_matching_tasks(text,text,integer) to service_role;

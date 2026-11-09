-- Every ingested/enriched complete vacancy is scored for eligible CV owners.
-- Discovery filters still organize browsing, but no longer silently skip scores.
create or replace function public.enqueue_matching_for_job(
  p_job_id uuid, p_model_id text, p_rubric_version text
)
returns integer language plpgsql security definer set search_path = public
as $$
declare
  v_job public.jobs%rowtype;
  v_user record;
  v_count integer := 0;
  v_hash text;
begin
  select * into v_job from public.jobs where id = p_job_id;
  if v_job.id is null or not v_job.is_active or v_job.description is null
     or length(btrim(v_job.description)) < 240
     or not (v_job.description ~* '(responsabil|mission|qualif|requirement|profile|avantage|benefit|skill)'
       or regexp_count(v_job.description, '[.!?]') >= 3) then
    return 0;
  end if;
  for v_user in
    select p.user_id, c.id as cv_document_id, c.content_hash
    from public.user_preferences p
    join public.cv_documents c on c.user_id = p.user_id and c.is_active
    where p.onboarding_completed_at is not null and length(btrim(c.extracted_text)) > 0
  loop
    v_hash := md5(jsonb_build_object('cv', v_user.content_hash, 'job', p_job_id,
      'description', v_job.description, 'model', p_model_id, 'rubric', p_rubric_version)::text);
    perform public.enqueue_gemini_analysis_atomic(v_user.user_id, p_job_id,
      v_user.cv_document_id, p_model_id, p_rubric_version, v_hash);
    v_count := v_count + 1;
  end loop;
  return v_count;
end;
$$;
revoke all on function public.enqueue_matching_for_job(uuid, text, text) from public, anon, authenticated;
grant execute on function public.enqueue_matching_for_job(uuid, text, text) to service_role;

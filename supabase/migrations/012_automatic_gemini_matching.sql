-- Additive queue entry point used by the authenticated local auto-match flow.
create or replace function public.enqueue_gemini_analysis_atomic(
  p_user_id uuid,
  p_job_id uuid,
  p_cv_document_id uuid,
  p_model_id text,
  p_rubric_version text,
  p_input_hash text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_queue_id uuid;
begin
  insert into public.job_analyses (
    user_id, job_id, cv_document_id, model_id, rubric_version, input_hash,
    status, score, result, error_message, updated_at
  ) values (
    p_user_id, p_job_id, p_cv_document_id, p_model_id, p_rubric_version,
    p_input_hash, 'pending', null, '{}'::jsonb, null, now()
  )
  on conflict (user_id, job_id, cv_document_id, model_id, rubric_version)
  do update set
    input_hash = excluded.input_hash,
    status = case
      when public.job_analyses.input_hash = excluded.input_hash
        and public.job_analyses.status = 'completed' then 'completed'
      else 'pending'
    end,
    score = case
      when public.job_analyses.input_hash = excluded.input_hash
        and public.job_analyses.status = 'completed' then public.job_analyses.score
      else null
    end,
    result = case
      when public.job_analyses.input_hash = excluded.input_hash
        and public.job_analyses.status = 'completed' then public.job_analyses.result
      else '{}'::jsonb
    end,
    error_message = null,
    updated_at = now();

  insert into public.gemini_analysis_queue (
    user_id, job_id, cv_document_id, model_id, rubric_version, input_hash,
    status, next_attempt_at, updated_at
  ) values (
    p_user_id, p_job_id, p_cv_document_id, p_model_id, p_rubric_version,
    p_input_hash, 'pending', now(), now()
  )
  on conflict (user_id, job_id, cv_document_id, model_id, rubric_version, input_hash)
  do update set
    status = case
      when public.gemini_analysis_queue.status = 'completed' then 'completed'
      when public.gemini_analysis_queue.status = 'processing' then 'processing'
      else public.gemini_analysis_queue.status
    end,
    next_attempt_at = case
      when public.gemini_analysis_queue.status in ('pending', 'processing', 'completed')
        then public.gemini_analysis_queue.next_attempt_at
      else now()
    end,
    updated_at = now()
  returning id into v_queue_id;

  if v_queue_id is null then
    select id into v_queue_id
    from public.gemini_analysis_queue
    where user_id = p_user_id and job_id = p_job_id
      and cv_document_id = p_cv_document_id and model_id = p_model_id
      and rubric_version = p_rubric_version and input_hash = p_input_hash;
  end if;
  return v_queue_id;
end;
$$;

revoke all on function public.enqueue_gemini_analysis_atomic(uuid, uuid, uuid, text, text, text) from public;
grant execute on function public.enqueue_gemini_analysis_atomic(uuid, uuid, uuid, text, text, text) to service_role;

update public.jobs
set description_status = case
  when description is not null and length(btrim(description)) >= 240
    and (description ~* '(responsabil|mission|qualif|requirement|profile|avantage|benefit|skill)')
    then 'complete'
  else 'needs_description'
end
where description_status is null or description_status = 'missing';

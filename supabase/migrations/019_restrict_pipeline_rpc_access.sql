-- Supabase's default privileges can grant EXECUTE directly to anon and
-- authenticated. Revoking PUBLIC alone does not remove these direct grants.
-- All these functions are called through authenticated server-side code.
revoke all on function public.claim_gemini_analysis_tasks(integer, text) from public, anon, authenticated;
revoke all on function public.reserve_gemini_api_slot(text, integer, integer, uuid) from public, anon, authenticated;
revoke all on function public.enqueue_gemini_analysis_atomic(uuid, uuid, uuid, text, text, text) from public, anon, authenticated;
revoke all on function public.enqueue_matching_for_job(uuid, text, text) from public, anon, authenticated;
revoke all on function public.record_staging_collector_state(text, text, uuid, text, text) from public, anon, authenticated;
revoke all on function public.ingest_job_atomic(text, text, text, text, text, text, text, text, text, text, timestamptz, timestamptz, jsonb) from public, anon, authenticated;

grant execute on function public.claim_gemini_analysis_tasks(integer, text) to service_role;
grant execute on function public.reserve_gemini_api_slot(text, integer, integer, uuid) to service_role;
grant execute on function public.enqueue_gemini_analysis_atomic(uuid, uuid, uuid, text, text, text) to service_role;
grant execute on function public.enqueue_matching_for_job(uuid, text, text) to service_role;
grant execute on function public.record_staging_collector_state(text, text, uuid, text, text) to service_role;
grant execute on function public.ingest_job_atomic(text, text, text, text, text, text, text, text, text, text, timestamptz, timestamptz, jsonb) to service_role;

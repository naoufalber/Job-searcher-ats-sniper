begin;
do $$
declare
  u uuid := gen_random_uuid();
  j uuid;
  c uuid;
  queued integer;
begin
  insert into auth.users(id,email) values(u,u::text || '@example.invalid');
  insert into public.user_preferences(user_id,target_roles,target_locations,onboarding_completed_at)
    values(u,array['Astronaut'],array['Moon'],now());
  insert into public.cv_documents(user_id,storage_path,original_name,mime_type,size_bytes,content_hash,extracted_text,is_active)
    values(u,u::text || '/test.pdf','test.pdf','application/pdf',1,'fixture','Local test fixture only',true) returning id into c;
  insert into public.jobs(canonical_url,company_name,title,location,description)
    values('https://example.invalid/' || u::text,'LOCAL FIXTURE','Data Scientist','Paris',repeat('plain ',60)) returning id into j;
  select public.enqueue_matching_for_job(j,'local-test','v1') into queued;
  if queued <> 0 then raise exception 'Insufficient description was queued'; end if;
  update public.jobs set description = 'Responsibilities and requirements: ' || repeat('Python SQL data science ',20) where id=j;
  perform public.enqueue_matching_for_job(j,'local-test','v1');
  perform public.enqueue_matching_for_job(j,'local-test','v1');
  if (select count(*) from public.gemini_analysis_queue where user_id=u and job_id=j) <> 1 then
    raise exception 'Complete job was skipped by preferences or queued twice';
  end if;
end;
$$;
rollback;

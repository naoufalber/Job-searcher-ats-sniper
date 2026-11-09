begin;
do $$
declare
  u uuid:=gen_random_uuid(); c uuid; j uuid; done_job uuid;
  old_task uuid; new_task uuid; done_task uuid; slot record; n integer;
  scope text:='cutover-test-'||gen_random_uuid()::text;
begin
  insert into auth.users(id,email) values(u,u::text||'@example.invalid');
  insert into public.cv_documents(user_id,storage_path,original_name,mime_type,size_bytes,content_hash,extracted_text,is_active)
    values(u,u::text||'/fixture.pdf','fixture.pdf','application/pdf',1,'fixture','Local fixture only',true) returning id into c;
  insert into public.jobs(canonical_url,company_name,title,description)
    values('https://example.invalid/pending/'||u::text,'LOCAL FIXTURE','Data Scientist','Responsibilities: '||repeat('Python and SQL. ',30)) returning id into j;
  insert into public.jobs(canonical_url,company_name,title,description)
    values('https://example.invalid/done/'||u::text,'LOCAL FIXTURE','Data Scientist','Responsibilities: '||repeat('Python and SQL. ',30)) returning id into done_job;
  old_task:=public.enqueue_gemini_analysis_atomic(u,j,c,'fixture-old','v1','old-hash');
  update public.gemini_analysis_queue set attempts=3 where id=old_task;
  done_task:=public.enqueue_gemini_analysis_atomic(u,done_job,c,'fixture-old','v1','done-hash');
  update public.gemini_analysis_queue set status='completed' where id=done_task;
  update public.job_analyses set status='completed',score=77 where user_id=u and job_id=done_job;
  n:=public.migrate_pending_matching_model('fixture-old','fixture-lite');
  if n<>1 then raise exception 'Incorrect pending migration count'; end if;
  if public.migrate_pending_matching_model('fixture-old','fixture-lite')<>0 then raise exception 'Migration not idempotent'; end if;
  if not exists(select 1 from public.gemini_analysis_queue where id=old_task and status='superseded' and attempts=3) then raise exception 'Old retry history lost'; end if;
  if not exists(select 1 from public.job_analyses where user_id=u and job_id=done_job and status='completed' and score=77) then raise exception 'Completed score changed'; end if;
  select id into new_task from public.gemini_analysis_queue where user_id=u and job_id=j and model_id='fixture-lite';
  perform public.defer_gemini_api_key(scope||':fixture-old',now()+interval '2 minutes','Old model quota exhausted');
  select * into slot from public.reserve_gemini_model_slot(scope,'fixture-old',10,60,new_task);
  if slot.allowed then raise exception 'Old model quota bypassed'; end if;
  select * into slot from public.reserve_gemini_model_slot(scope,'fixture-lite',10,60,new_task);
  if not slot.allowed then raise exception 'Old cooldown incorrectly blocked new model'; end if;
  for n in 2..10 loop
    perform public.reserve_gemini_model_slot(scope,'fixture-other',10,60,new_task);
  end loop;
  select * into slot from public.reserve_gemini_model_slot(scope,'fixture-lite',10,60,new_task);
  if slot.allowed then raise exception 'Global ten RPM exceeded across models'; end if;
end;
$$;
rollback;

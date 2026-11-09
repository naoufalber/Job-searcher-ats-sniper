-- Local rollback-only test. No Gemini request is made.
begin;
do $$
declare
  u uuid:=gen_random_uuid(); c uuid; j uuid; q uuid; slot record;
  scope text:='daily-test-'||gen_random_uuid()::text;
  existing integer; attempts_before integer;
begin
  insert into auth.users(id,email) values(u,u::text||'@example.invalid');
  select id into j from public.jobs limit 1;
  insert into public.cv_documents(user_id,storage_path,original_name,mime_type,size_bytes,content_hash,extracted_text)
    values(u,u::text||'/daily.pdf','daily.pdf','application/pdf',1,'daily-test','Local fixture') returning id into c;
  insert into public.gemini_analysis_queue(user_id,job_id,cv_document_id,model_id,rubric_version,input_hash)
    values(u,j,c,'daily-test','v1','daily-test') returning id into q;
  select count(*) into existing from public.gemini_api_attempts where api_key_scope<>'local-mock' and attempted_at>now()-interval '24 hours';
  if existing>449 then raise exception 'Local test requires fewer than 450 existing attempts'; end if;
  insert into public.gemini_api_attempts(api_key_scope,queue_id,attempted_at)
    select scope,q,now()-interval '1 hour' from generate_series(1,449-existing);
  select * into slot from public.reserve_gemini_model_slot(scope,'daily-test',10,60,q);
  if not slot.allowed then raise exception '450th attempt should be allowed'; end if;
  select attempts into attempts_before from public.gemini_analysis_queue where id=q;
  select * into slot from public.reserve_gemini_model_slot(scope||'-rotated-key','different-model',10,60,q);
  if slot.allowed or slot.wait_seconds<=60 then raise exception 'Rotating keys/models bypassed the daily cap'; end if;
  if (select attempts from public.gemini_analysis_queue where id=q)<>attempts_before then raise exception 'Blocked daily attempt changed retry count'; end if;
  select * into slot from public.reserve_gemini_api_slot(scope||'-other-worker',10,60,q);
  if slot.allowed then raise exception 'Direct reservations bypassed daily cap'; end if;
  update public.gemini_api_attempts set attempted_at=now()-interval '25 hours' where api_key_scope=scope;
  select * into slot from public.reserve_gemini_model_slot(scope||'-new','daily-test',10,60,q);
  if not slot.allowed then raise exception 'Expired usage did not release capacity'; end if;
  if has_function_privilege('authenticated','public.reserve_gemini_api_slot(text,integer,integer,uuid)','execute') then raise exception 'Privileged limiter exposed'; end if;
end;
$$;
rollback;

-- Local-only transaction: every fixture and attempt is rolled back.
begin;
do $$
declare
  u uuid := gen_random_uuid();
  c uuid;
  q uuid;
  j uuid;
  scope text := 'local-test-' || gen_random_uuid()::text;
  slot record;
  i integer;
begin
  insert into auth.users(id, email) values (u, u::text || '@example.invalid');
  select id into j from public.jobs limit 1;
  if j is null then raise exception 'Local fixture job required'; end if;
  insert into public.cv_documents(user_id, storage_path, original_name, mime_type, size_bytes, content_hash, extracted_text)
    values(u, u::text || '/quota-test.pdf', 'quota-test.pdf', 'application/pdf', 1, 'local-test', 'Local policy fixture only') returning id into c;
  insert into public.gemini_analysis_queue(user_id, job_id, cv_document_id, model_id, rubric_version, input_hash)
    values(u, j, c, 'local-test', 'v1', 'local-test') returning id into q;
  insert into public.gemini_api_attempts(api_key_scope, queue_id, attempted_at)
    values(scope, q, now() - interval '12 hours');
  perform public.defer_gemini_api_key(scope,now()+interval '5 minutes','Gemini quota exhausted.');
  select * into slot from public.reserve_gemini_api_slot(scope,10,60,q);
  if slot.allowed or slot.wait_seconds<>300 then raise exception 'Shared cooldown was not honored'; end if;
  if (select count(*) from public.gemini_api_attempts where api_key_scope=scope)<>1 then
    raise exception 'A blocked reservation consumed an attempt';
  end if;
  update public.gemini_api_cooldowns set blocked_until=now()-interval '1 second' where api_key_scope=scope;
  for i in 1..10 loop
    select * into slot from public.reserve_gemini_api_slot(scope, 14, 60, q);
    if not slot.allowed then raise exception 'Request % unexpectedly blocked', i; end if;
  end loop;
  select * into slot from public.reserve_gemini_api_slot(scope, 14, 60, q);
  if slot.allowed or slot.wait_seconds <> 60 then raise exception '11th request was not correctly delayed'; end if;
  if (select count(*) from public.gemini_api_attempts where api_key_scope = scope) <> 11 then
    raise exception 'Daily-budget history was lost';
  end if;
  update public.gemini_api_attempts set attempted_at = now() - interval '59 seconds'
    where id = (select min(id) from public.gemini_api_attempts where api_key_scope = scope and attempted_at > now() - interval '1 minute');
  select * into slot from public.reserve_gemini_api_slot(scope, 14, 60, q);
  if slot.allowed or slot.wait_seconds <> 1 then raise exception 'Did not wait only for earliest slot'; end if;
  if has_function_privilege('anon', 'public.reserve_gemini_api_slot(text,integer,integer,uuid)', 'execute') then
    raise exception 'Anonymous quota reservation unexpectedly allowed';
  end if;
end;
$$;
rollback;

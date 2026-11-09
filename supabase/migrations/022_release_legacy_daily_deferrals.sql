-- The old daily cap could also defer a task with an earlier transient error.
-- Its recognizable 24-hour deadline differs from provider backoff (<=15 min).
-- Keep the error and attempt history; only release this obsolete budget wait.
update public.gemini_analysis_queue
set next_attempt_at = now(), updated_at = now()
where status = 'pending'
  and next_attempt_at > now() + interval '1 hour'
  and extract(epoch from (next_attempt_at - updated_at)) between 86398 and 86402;

create policy "users update own gemini queue" on public.gemini_analysis_queue
  for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

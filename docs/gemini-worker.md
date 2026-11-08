# Local Gemini queue worker

The browser and Next.js API never call Gemini directly. `POST /api/ai/analyze` authenticates the user, validates the job/CV, checks the completed cache, and atomically enqueues a task in Supabase. The worker is the only process allowed to use `GEMINI_API_KEY`.

The database limiter uses an advisory lock per hashed API-key scope, records every actual attempt in `gemini_api_attempts`, and permits at most `GEMINI_RATE_LIMIT_RPM` attempts during the previous 60 seconds. The default is 14. If the window is full, the task is returned to `pending` until the earliest recorded attempt expires; the worker does not sleep for a fixed minute or busy-poll.

From PowerShell, with local Supabase and the Next.js environment loaded:

```powershell
cd apps/web
npm run gemini:worker
# bounded smoke run
npm run gemini:worker:once
```

For a no-network queue smoke test, set `GEMINI_MOCK_RESPONSE` to a valid analysis JSON object. In mock mode the worker uses the same queue, database rate reservation, persistence, and cache paths but makes no Gemini request:

```powershell
$env:GEMINI_MOCK_RESPONSE = '{"score":82,"confidence":"high","matching_skills":[{"skill":"Python","evidence":"CV and job both mention Python."}],"missing_required_skills":[],"experience_gaps":[],"education_gaps":[],"language_location_considerations":[],"explanation":"Mocked local result.","cv_adaptation_suggestions":[],"recommended_action":"Apply"}'
npm run gemini:worker
```

Required server-only variables are `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `GEMINI_API_KEY`. Optional variables are `GEMINI_RATE_LIMIT_RPM` (default `14`), `GEMINI_MAX_ATTEMPTS` (default `5`), `GEMINI_MODEL`, and `GEMINI_RUBRIC_VERSION`.

The 14 RPM value is a safety ceiling for this worker, not a guarantee of successful Gemini calls. Other consumers of the same API key consume the same provider quota, and daily request, tokens-per-minute, model, and billing limits still apply. Lower the value if the key is shared; never raise it above the provider's effective quota without confirming the quota and all other consumers.

The worker honors numeric or HTTP-date `Retry-After` values for 429 responses. Network and 5xx failures use bounded exponential backoff with jitter. Permanent 4xx responses and invalid model JSON are marked failed. Claimed tasks older than ten minutes are reclaimable after a worker restart.

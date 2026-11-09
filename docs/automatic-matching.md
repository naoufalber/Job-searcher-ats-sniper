# Automatic local CV matching

## Hosted automation

The production `sniper.yml` workflow is the single scheduled collector (`*/5 * * * *`, UTC).
The staging collector is manual-only. Both use the authenticated Vercel ingestion API;
the deployed application and Gemini worker use Supabase Cloud, so the pipeline does
not require a running laptop, local Docker, or local Supabase.

The Gemini workflow runs after a successful production collector run on `main`,
and also has a 15-minute fallback schedule (`7,22,37,52 * * * *`, UTC). GitHub schedules
are best effort; a configured cron is not evidence that a particular scheduled run executed.
Worker concurrency is serialized. Each run drains the queue for up to eleven minutes,
using a database-enforced ceiling of ten actual attempts per rolling minute. There
is no application-imposed daily request cap or two-task batch cap. When capacity
is exhausted, the worker waits for the next available slot; pending work persists
between runs. Provider daily/token quotas still apply, and 429/5xx responses retain
bounded retry state. No paid billing configuration is enabled by these settings.

Automatic eligibility requires an active CV and completed onboarding preferences.
Role/location browsing filters do not exclude newly ingested jobs from matching. A description must
contain at least 240 characters plus section signals or three sentence markers
before ingestion queues a match. Missing descriptions remain visible and use the
collector's bounded enrichment retries; blocked pages are never bypassed.

Later description updates are delivered independently of notification delivery.
Previously delivered payloads are reconciled once when their delivered-description
snapshot is absent. Pending ingestion preserves its attempt count and retry deadline.
Never-delivered vacancies take priority over updates to previously delivered jobs.
Reaching a scan's detail budget defers enrichment without consuming a failed attempt.

Manual analysis and automatic matching use the same PostgreSQL-compatible cache
key (CV content hash, job ID, description, model, rubric). Matching POST requests use
the atomic database enqueue function. Reopening an analysis only reads saved results.
Migrations 018–021 preserve quota history, enforce ten RPM, and restrict internal pipeline RPCs to
the service role; credentials remain on the server.

Read-only diagnostics (provide Supabase credentials only through the process environment):

```powershell
node scripts/audit-pipeline.mjs 2026-11-09T12:06:00Z
```

Local quota/RPC regression, with all fixture writes rolled back:

```powershell
Get-Content -Raw supabase/tests/gemini_quota.sql |
  docker exec -i supabase_db_ats-sniper-local psql -U postgres -d postgres -v ON_ERROR_STOP=1
```

## Local development

Automatic matching is disabled by default:

```dotenv
ATS_AUTO_MATCH_ENABLED=false
```

For a bounded local test, set the authenticated local user's UUID and enable it only in the current PowerShell process:

```powershell
$env:ATS_AUTO_MATCH_ENABLED = "true"
$env:ATS_AUTO_MATCH_USER_ID = "<local-authenticated-user-uuid>"
$env:ATS_AUTO_MATCH_BACKFILL_LIMIT = "5"
```

Restart Next.js after changing these variables. A newly ingested job with a complete description is then written to the persistent Gemini queue for that user and active CV. The ingestion request never calls Gemini.

Jobs with incomplete descriptions receive `needs_description` and remain visible. They are not queued for Gemini. A later enrichment update can set the job to `complete` and enqueue a new task using the same atomic function.

To queue at most five relevant historical jobs without making Gemini calls from the command:

```powershell
node scripts/auto-match-backfill.mjs
```

The worker remains the only Gemini caller:

```powershell
cd apps/web
npm run gemini:worker
```

Use `GEMINI_RATE_LIMIT_RPM=10` (the database also caps reservations at ten). Missing-description rows display a recorded provider error, budget deferral, or an explicit message that extraction details have not yet been recorded. No scores are fabricated.

## Queue timing and contract extraction

The hosted worker processes one task at a time, immediately starting the next task after a response unless the database's rolling ten-attempt/minute limit or provider retry guidance requires waiting. Each run is bounded to 660 seconds; unfinished tasks stay in PostgreSQL for the next run. GitHub Actions schedules can be delayed, so queued does not mean an API request is currently running. Ten RPM is shared across users and includes retries: 180 tasks require at least about 18 minutes of active worker time.

The same Gemini response now includes `contract_type` and a verbatim `contract_evidence` quote from the job title or description. Unknown or conflicting contracts remain null. The worker rejects evidence not found in those job fields. These values are stored in `job_analyses.result`; the jobs table displays them as an AI-labeled fallback when provider contract metadata is absent. Provider values take precedence, and contract filters continue to use provider metadata. Existing cached results are not regenerated for this optional field. No additional Gemini request or database migration is required.

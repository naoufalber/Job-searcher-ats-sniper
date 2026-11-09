# Automatic local CV matching

## Hosted automation

The production `sniper.yml` workflow is the single scheduled collector (`*/5 * * * *`, UTC).
The staging collector is manual-only. Both use the authenticated Vercel ingestion API;
the deployed application and Gemini worker use Supabase Cloud, so the pipeline does
not require a running laptop, local Docker, or local Supabase.

The Gemini workflow runs after a successful production collector run on `main`,
and also has a 15-minute fallback schedule (`7,22,37,52 * * * *`, UTC). GitHub schedules
are best effort; a configured cron is not evidence that a particular scheduled run executed.
Worker concurrency is serialized. Each run considers at most two tasks, uses the
database-enforced 14-attempt rolling-minute limit, and keeps the existing conservative
two-attempt daily budget. Consequently, additional analyses can remain queued until
budget becomes available. Do not increase that budget without checking the API project's
daily/token quotas and billing configuration.

Automatic eligibility requires an active CV and completed onboarding preferences.
The current SQL matches target role text and target locations. A description must
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
Migrations 018 and 019 preserve quota history and restrict internal pipeline RPCs to
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

Keep `GEMINI_RATE_LIMIT_RPM=14` or lower. Do not enable the toggle for bulk historical runs. The Discover page shows score, pending, failed, CV-required, and needs-description states without assigning fake scores.

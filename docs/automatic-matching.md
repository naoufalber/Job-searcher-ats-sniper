# Automatic local CV matching

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

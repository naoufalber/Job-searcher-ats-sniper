# Local job-description enrichment

`scripts/enrich_jobs.py` reads existing jobs through the local Supabase REST API and updates only missing metadata. It never opens or writes `jobs_seen.db`, never calls Discord/Telegram, and refuses non-local Supabase URLs.

The completeness rule is explicit: at least 240 cleaned characters plus either three sentence terminators or two responsibility/qualification/mission/profile signals. A non-null title or one-line snippet is not considered complete.

PowerShell workflow:

```powershell
cd C:\path\to\Job-searcher-ats-sniper
$env:NEXT_PUBLIC_SUPABASE_URL = "http://127.0.0.1:54321"
$env:SUPABASE_SERVICE_ROLE_KEY = "<local service-role key>"

# inspect the first five eligible jobs without changing Supabase
python scripts/enrich_jobs.py --dry-run --limit 5

# enrich at most five jobs
python scripts/enrich_jobs.py --limit 5

# retry rows recorded as provider failures
python scripts/enrich_jobs.py --retry-failed --limit 5

# restrict a batch to one provider
python scripts/enrich_jobs.py --provider greenhouse --limit 5
```

The script uses public SmartRecruiters, Lever, Greenhouse, and Ashby API routes where the canonical URL identifies the provider. Workday, HelloWork, and Welcome to the Jungle use the public detail page and JSON-LD when present. It does not bypass authentication, CAPTCHA, robots restrictions, or anti-bot controls. A provider failure is stored as `provider_unavailable` or `extraction_failed` and processing continues.

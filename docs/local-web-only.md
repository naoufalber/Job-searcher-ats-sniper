# Local web-only collector mode

This mode runs the existing provider collectors against a separate SQLite state
file and sends normalized jobs only to the local Next.js ingestion endpoint. It
never calls Discord or Telegram.

Providers currently scanned:

- SmartRecruiters
- Lever
- Greenhouse
- Ashby
- Workday
- HelloWork
- Welcome to the Jungle

The provider adapters retain their current request retry policy and timeout. In
web-only mode each provider is isolated: an exception in one provider is logged
and the remaining providers continue.

## Start local services

From the repository root, start Docker Desktop first, then:

```powershell
$env:SUPABASE_TELEMETRY_DISABLED = "true"
.\apps\web\node_modules\.bin\supabase.cmd start

$envText = & .\apps\web\node_modules\.bin\supabase.cmd status -o env
$local = @{}
foreach ($line in $envText) {
  if ($line -match '^([A-Z0-9_]+)=(.*)$') {
    $local[$Matches[1]] = $Matches[2].Trim('"')
  }
}
$env:NEXT_PUBLIC_SUPABASE_URL = $local["API_URL"]
$env:NEXT_PUBLIC_SUPABASE_ANON_KEY = $local["ANON_KEY"]
$env:SUPABASE_SERVICE_ROLE_KEY = $local["SERVICE_ROLE_KEY"]
$env:ATS_INGESTION_SHARED_SECRET = "local-test-ingestion-secret"

Set-Location apps\web
npm run dev -- --port 3000
```

Run the collector from a second PowerShell window. The collector only needs the
shared secret; the service-role key stays in the Next.js server environment.

```powershell
cd "C:\Users\Naoufal BENKMIL\Desktop\Job-searcher-ats-sniper"
$env:ATS_INGESTION_API_URL = "http://127.0.0.1:3000"
$env:ATS_INGESTION_SHARED_SECRET = "local-test-ingestion-secret"
$env:ATS_WEB_ONLY_DB_FILE = "local_jobs_seen.db"
```

## Run one bounded scan

```powershell
python ats_sniper.py --web-only
```

The command prints per-provider discovery counts and a final
`notifications=disabled` summary. It does not touch the tracked `jobs_seen.db`.

## Run continuous polling

Start only after the one-time scan is understood:

```powershell
python ats_sniper.py --web-only --loop
```

The default interval is five minutes. Stop it with `Ctrl+C`; the handler exits
without deleting the local state file. Re-running the command reuses the same
`local_jobs_seen.db` and its deduplication/retry state.

## Stop services

Stop the collector with `Ctrl+C`, stop Next.js with `Ctrl+C`, then from the
repository root:

```powershell
$env:SUPABASE_TELEMETRY_DISABLED = "true"
.\apps\web\node_modules\.bin\supabase.cmd stop
```

Do not run `supabase db reset` for ordinary restarts. The local database and
the separate `local_jobs_seen.db` are persistent across stop/start cycles.

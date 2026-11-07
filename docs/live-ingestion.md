# Additive ATS Sniper ingestion

The collector now has an opt-in Supabase output. It is disabled unless both of these environment variables are present:

```text
ATS_INGESTION_API_URL=http://127.0.0.1:3000
ATS_INGESTION_SHARED_SECRET=<server-only shared secret>
```

The Next.js ingestion route additionally requires:

```text
SUPABASE_SERVICE_ROLE_KEY=<server-only local or hosted key>
ATS_INGESTION_SHARED_SECRET=<same shared secret>
```

The service-role key and shared secret must never use `NEXT_PUBLIC_*`, browser code, source control, or notification payloads.

## Data flow

```text
provider scanner
  -> existing matches_criteria filter
  -> existing SQLite seen_jobs deduplication
  -> existing Discord/Telegram behavior
  -> local SQLite supabase_ingestion_queue
  -> POST /api/ingest/jobs
  -> service-role Supabase upsert
```

The queue is created additively by `init_db()`. A failed ingestion remains pending with an attempt count, error, and exponential retry time. Notification state is stored separately in `seen_jobs`; a Supabase failure cannot turn a successful notification into a failed notification or block the notification pipeline.

## Stored fields

The normalized payload contains only values available from the collector:

- Provider/source.
- Existing provider-prefixed job identifier.
- Company, title, location, and canonical URL.
- Description and experience metadata when the provider exposes them.
- Country inferred only when the location explicitly contains France/FR.
- Remote inferred only when the location explicitly contains “remote”.
- Contract type and publication date remain null unless a future provider adapter supplies them.
- `first_seen_at` is discovery time, not source publication time.

## Local testing

Start local Supabase and the web server with a local-only service key and shared secret. Then run:

```powershell
cd apps/web
npm run test:ingestion
```

The tests reject non-local URLs and cover unauthorized requests, invalid payloads, and idempotent duplicate ingestion. Python queue tests are part of `test_ats_sniper.py` and should be run with `python -m unittest -v` when Python is available.

## Enabling the collector output later

The existing `.github/workflows/sniper.yml` is intentionally unchanged. To activate ingestion in GitHub Actions later, add these secrets/environment variables to the existing collector job:

```text
ATS_INGESTION_API_URL
ATS_INGESTION_SHARED_SECRET
```

The route’s server environment must also contain the matching `ATS_INGESTION_SHARED_SECRET` and a Supabase service-role key. This activation requires a separate review because it changes the production collector’s outbound calls. Keep ingestion disabled until the endpoint, rate limits, and failure behavior are approved.

## Historical backfill

The current `jobs_seen.db` contains 21 rows, all marked `sent`, with the latest observed detection timestamp on 2026-10-27. There are no repository logs containing the original notification bodies or full job descriptions. As a result, an accurate last-24-hour backfill is not currently possible from the repository state. Existing rows can be re-enqueued only as historical discoveries with their existing `detected_at` values; they must not be presented as newly published jobs or re-notified.

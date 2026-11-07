# Full-stack application foundation

This repository now contains an additive Next.js application under `apps/web/` and a versioned Supabase migration under `supabase/migrations/`.

## Boundaries

- `ats_sniper.py`, `test_ats_sniper.py`, `jobs_seen.db`, and `.github/workflows/sniper.yml` remain the production collector boundary.
- The web application reads normalized jobs from Supabase when the public Supabase environment variables are configured.
- The collector-to-Supabase ingestion path is intentionally not implemented in this phase.
- The existing Discord and Telegram notification flow remains untouched.

## Future ingestion contract

The future adapter should normalize each accepted collector result to:

```json
{
  "source": "smartrecruiters",
  "external_job_id": "744000156036969",
  "company_name": "Example",
  "title": "Data Engineer",
  "location": "Paris, France",
  "canonical_url": "https://example.test/job",
  "description": null,
  "experience_level": null,
  "remote_type": null,
  "metadata": {}
}
```

The safest later integration point is after `matches_criteria()` and before notification delivery. The integration must be best-effort and isolated: a Supabase failure must be logged and must not prevent the existing notification or SQLite state transition. That change requires a separate authorization.

## Local setup

```bash
cd apps/web
npm install
copy .env.example .env.local
npm run dev
```

Set only the public Supabase URL and anon key in `.env.local`. Never put a service-role key in browser-exposed variables.

## Database setup

Apply `supabase/migrations/001_initial_schema.sql` only to an explicitly approved Supabase project. This task did not create a project, execute remote migrations, or access production credentials.

## Current limitations

- No collector ingestion yet.
- No production Supabase data is assumed or fabricated.
- Authentication is represented by a magic-link page; redirect and middleware hardening should be completed with the chosen Supabase project configuration.
- A lockfile is not present because dependencies were not installed in this task.

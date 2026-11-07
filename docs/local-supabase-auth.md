# Local Supabase Auth development

This workflow uses the Supabase CLI's local Docker stack and its bundled Mailpit email inbox. It does not send real email and does not require a hosted Supabase project.

## Prerequisites

- Docker Desktop running.
- Node.js and npm available for the web app.
- Supabase CLI 3.0.0 installed locally as a web-app dev dependency by `npm ci`.

The project uses the locally installed Supabase CLI 3.0.0. Do not install a second email service: Mailpit is part of the local Supabase stack.

## Start the local stack

From the repository root:

```powershell
.\scripts\supabase-local.ps1 start
.\scripts\supabase-local.ps1 status
```

The checked-in configuration uses the standard local endpoints:

| Service | URL/port |
|---|---|
| Supabase API/Auth | `http://127.0.0.1:54321` |
| PostgreSQL | `127.0.0.1:54322` |
| Studio | `http://127.0.0.1:54323` |
| Mailpit inbox | `http://127.0.0.1:54324` |
| SMTP capture | `127.0.0.1:54325` |

Use only the local anon key from the status output in the browser environment. Never put the local `service_role` key in `NEXT_PUBLIC_*` variables.

## Apply migrations and deterministic fixtures

The safe reset command targets the local CLI database only:

```powershell
.\scripts\supabase-local.ps1 reset
```

Equivalent local CLI command:

```powershell
cd apps/web
npx supabase db reset
```

This reapplies every migration and `supabase/seed.sql`. The seed contains one clearly marked fixture job and no production data.

Never use `supabase db push`, `supabase link`, or a hosted database URL in this local reset workflow.

## Configure Next.js for local Supabase

Create `apps/web/.env.local` (ignored by Git):

```dotenv
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key from supabase status>
```

Start the web app:

```powershell
cd apps/web
npm ci
npm run dev
```

The browser uses only the local URL and anon key. The server-side client also uses the anon key; privileged keys are intentionally absent from the application.

## Inspect captured email

Open `http://127.0.0.1:54324` in a browser. Signup confirmation and password-recovery emails appear in Mailpit. They are captured locally and are never delivered to real recipients.

## Run the authentication integration tests

From the repository root, obtain the local anon key from `supabase status`, then set it only in the current shell:

```powershell
$env:LOCAL_SUPABASE_URL = 'http://127.0.0.1:54321'
$env:LOCAL_SUPABASE_ANON_KEY = '<anon key from supabase status>'
$env:LOCAL_INBUCKET_URL = 'http://127.0.0.1:54324'
cd apps/web
npm run test:auth
```

The test suite covers:

- Signup with required email confirmation.
- Confirmation-link capture and verification.
- Password login.
- Logout.
- Session persistence across client instances.
- Password-recovery email capture and password change.
- User-owned RLS access.

Tests refuse to run if `LOCAL_SUPABASE_URL` is not localhost/127.0.0.1. They do not use a service-role key or hosted admin API.

## Stop and clean up

```powershell
.\scripts\supabase-local.ps1 stop
```

The normal reset command is sufficient for repeatable test data and is less destructive than removing all Docker volumes.

## Local versus hosted environments

| Environment | URL variable | Key variable | Migration/reset policy |
|---|---|---|---|
| Local | `http://127.0.0.1:54321` | Local anon key | `supabase db reset` is allowed |
| Hosted staging | Staging project URL | Staging anon key | Apply reviewed migrations through approved staging process |
| Hosted production | Production project URL | Production anon key | Never reset; deploy reviewed migrations only |

Use separate `.env.local` files or secret-manager entries per environment. Keep only names and safe placeholders in `.env.example`. Do not put service-role keys in client variables, source control, browser bundles, or test fixtures.

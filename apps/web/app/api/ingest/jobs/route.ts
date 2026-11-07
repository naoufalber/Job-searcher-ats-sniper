import { NextResponse } from "next/server";
import { timingSafeEqual } from "node:crypto";
import { createAdminClient } from "@/lib/supabase/admin";
import { jobIngestionSchema } from "@/lib/validation";

export const runtime = "nodejs";

function authorized(request: Request) {
  const expected = process.env.ATS_INGESTION_SHARED_SECRET;
  const received = request.headers.get("x-ats-ingestion-secret");
  if (!expected || !received) return false;
  const expectedBytes = Buffer.from(expected);
  const receivedBytes = Buffer.from(received);
  return expectedBytes.length === receivedBytes.length && timingSafeEqual(expectedBytes, receivedBytes);
}

export async function POST(request: Request) {
  const length = Number(request.headers.get("content-length") ?? 0);
  if (length > 262144) return NextResponse.json({ error: "Payload too large." }, { status: 413 });
  if (!authorized(request)) return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  const admin = createAdminClient();
  if (!admin) return NextResponse.json({ error: "Ingestion is not configured." }, { status: 503 });
  let body: unknown;
  try {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).byteLength > 262144) {
      return NextResponse.json({ error: "Payload too large." }, { status: 413 });
    }
    body = JSON.parse(raw);
  } catch { return NextResponse.json({ error: "Invalid JSON." }, { status: 400 }); }
  const parsed = jobIngestionSchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: "Invalid job payload.", details: parsed.error.flatten() }, { status: 422 });
  const job = parsed.data;
  const { data, error } = await admin.rpc("ingest_job_atomic", {
    p_source: job.source,
    p_external_job_id: job.external_job_id,
    p_company_name: job.company_name,
    p_title: job.title,
    p_location: job.location ?? null,
    p_country: job.country ?? null,
    p_contract_type: job.contract_type ?? null,
    p_remote_type: job.remote_type ?? null,
    p_canonical_url: job.canonical_url,
    p_description: job.description ?? null,
    p_first_seen_at: job.first_seen_at ?? null,
    p_publication_date: job.publication_date ?? null,
    p_metadata: job.metadata,
  }).single();
  if (error || !data) return NextResponse.json({ error: "Unable to persist job." }, { status: 502 });
  const result = data as unknown as { result_job_id: string; result_source_id: number };
  return NextResponse.json({ ok: true, job_id: result.result_job_id, source_id: result.result_source_id });
}

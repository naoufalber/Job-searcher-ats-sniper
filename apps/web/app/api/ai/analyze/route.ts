import "server-only";
import { createHash } from "node:crypto";
import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { analysisInputHash, isDescriptionComplete } from "@/lib/analysis";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const supabase = createClient();
  if (!supabase) return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  const { data: auth } = await supabase.auth.getUser();
  const jobId = new URL(request.url).searchParams.get("jobId");
  if (!auth.user || !jobId) return NextResponse.json({ error: "Unauthorized or missing job id." }, { status: 401 });
  const { data: queue } = await supabase.from("gemini_analysis_queue").select("id,status,attempts,next_attempt_at,last_error,updated_at").eq("user_id", auth.user.id).eq("job_id", jobId).order("updated_at", { ascending: false }).limit(1).maybeSingle();
  const { data: analysis } = await supabase.from("job_analyses").select("id,status,score,result,error_message,updated_at").eq("user_id", auth.user.id).eq("job_id", jobId).order("updated_at", { ascending: false }).limit(1).maybeSingle();
  return NextResponse.json({ queue, analysis });
}

export async function POST(request: Request) {
  const supabase = createClient();
  if (!supabase) return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  const body = await request.json().catch(() => null) as { jobId?: string; cvDocumentId?: string } | null;
  if (!body?.jobId || !/^[0-9a-f-]{36}$/i.test(body.jobId)) return NextResponse.json({ error: "Invalid job id." }, { status: 422 });
  const [{ data: job }, { data: cv }] = await Promise.all([
    supabase.from("jobs").select("id,title,company_name,location,description").eq("id", body.jobId).maybeSingle(),
    body.cvDocumentId ? supabase.from("cv_documents").select("id,content_hash,extracted_text").eq("id", body.cvDocumentId).eq("user_id", auth.user.id).maybeSingle() : supabase.from("cv_documents").select("id,content_hash,extracted_text").eq("user_id", auth.user.id).eq("is_active", true).maybeSingle(),
  ]);
  if (!job) return NextResponse.json({ error: "Job not found." }, { status: 404 });
  if (!cv) return NextResponse.json({ error: "Upload an active CV first." }, { status: 422 });
  if (!isDescriptionComplete(job.description)) return NextResponse.json({ status: "insufficient", error: "This job does not contain enough description text for a reliable analysis." }, { status: 422 });
  const model = process.env.GEMINI_MODEL || "gemini-2.0-flash";
  const rubric = process.env.GEMINI_RUBRIC_VERSION || "v1";
  const inputHash = analysisInputHash(cv.content_hash, job.id, job.description!, model, rubric);
  const legacyHash = createHash("sha256").update(JSON.stringify({ cv: cv.content_hash, job: job.id, description: job.description, model, rubric })).digest("hex");
  const { data: cached } = await supabase.from("job_analyses").select("id,status,score,result,error_message,updated_at").eq("user_id", auth.user.id).eq("job_id", job.id).eq("cv_document_id", cv.id).eq("model_id", model).eq("rubric_version", rubric).in("input_hash", [inputHash, legacyHash]).maybeSingle();
  if (cached?.status === "completed") return NextResponse.json({ status: "completed", analysis: cached, cached: true });
  if (!process.env.GEMINI_API_KEY && !process.env.GEMINI_MOCK_RESPONSE) return NextResponse.json({ error: "AI matching is not configured locally." }, { status: 503 });
  const admin = createAdminClient();
  if (!admin) return NextResponse.json({ error: "Analysis queue is unavailable." }, { status: 503 });
  const { data: queueId, error: queueError } = await admin.rpc("enqueue_gemini_analysis_atomic", { p_user_id: auth.user.id, p_job_id: job.id, p_cv_document_id: cv.id, p_model_id: model, p_rubric_version: rubric, p_input_hash: inputHash });
  if (queueError || !queueId) return NextResponse.json({ error: "Unable to queue analysis." }, { status: 500 });
  const { data: queued } = await supabase.from("gemini_analysis_queue").select("id,status,attempts,next_attempt_at,last_error,updated_at").eq("id", queueId).single();
  return NextResponse.json({ status: queued?.status ?? "pending", queue: queued }, { status: 202 });
}

import "server-only";
import { createHash } from "node:crypto";
import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

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
  if (!job.description || job.description.trim().length < 120) return NextResponse.json({ status: "insufficient", error: "This job does not contain enough description text for a reliable analysis." }, { status: 422 });
  const model = process.env.GEMINI_MODEL || "gemini-2.0-flash";
  const rubric = process.env.GEMINI_RUBRIC_VERSION || "v1";
  const inputHash = createHash("sha256").update(JSON.stringify({ cv: cv.content_hash, job: job.id, description: job.description, model, rubric })).digest("hex");
  const { data: cached } = await supabase.from("job_analyses").select("id,status,score,result,error_message,updated_at").eq("user_id", auth.user.id).eq("job_id", job.id).eq("cv_document_id", cv.id).eq("model_id", model).eq("rubric_version", rubric).eq("input_hash", inputHash).maybeSingle();
  if (cached?.status === "completed") return NextResponse.json({ status: "completed", analysis: cached, cached: true });
  if (!process.env.GEMINI_API_KEY && !process.env.GEMINI_MOCK_RESPONSE) return NextResponse.json({ error: "AI matching is not configured locally." }, { status: 503 });
  const { data: analysis, error: analysisError } = await supabase.from("job_analyses").upsert({ user_id: auth.user.id, job_id: job.id, cv_document_id: cv.id, model_id: model, rubric_version: rubric, input_hash: inputHash, status: "pending", score: null, result: {}, error_message: null, updated_at: new Date().toISOString() }, { onConflict: "user_id,job_id,cv_document_id,model_id,rubric_version" }).select("id,status,score,result,error_message,updated_at").single();
  if (analysisError || !analysis) return NextResponse.json({ error: "Unable to queue analysis." }, { status: 500 });
  const { data: queued, error: queueError } = await supabase.from("gemini_analysis_queue").upsert({ user_id: auth.user.id, job_id: job.id, cv_document_id: cv.id, model_id: model, rubric_version: rubric, input_hash: inputHash, status: "pending", next_attempt_at: new Date().toISOString(), updated_at: new Date().toISOString() }, { onConflict: "user_id,job_id,cv_document_id,model_id,rubric_version,input_hash" }).select("id,status,attempts,next_attempt_at,last_error,updated_at").single();
  if (queueError || !queued) return NextResponse.json({ error: "Unable to queue analysis." }, { status: 500 });
  return NextResponse.json({ status: queued.status, queue: queued, analysis }, { status: 202 });
}

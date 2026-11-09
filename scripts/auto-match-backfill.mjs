import { createRequire } from "node:module";
import { resolve } from "node:path";
import { analysisInputHash } from "../apps/web/lib/matching-input.mjs";

const { createClient } = createRequire(resolve(process.cwd(), "apps", "web", "package.json"))("@supabase/supabase-js");
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
const userId = process.env.ATS_AUTO_MATCH_USER_ID;
const limit = Math.min(Math.max(Number.parseInt(process.env.ATS_AUTO_MATCH_BACKFILL_LIMIT || "5", 10) || 5, 1), 5);
if (!url || !key || !userId) throw new Error("NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and ATS_AUTO_MATCH_USER_ID are required.");
const supabase = createClient(url, key, { auth: { autoRefreshToken: false, persistSession: false } });
const model = process.env.GEMINI_MODEL || "gemini-3.5-flash-lite";
const rubric = process.env.GEMINI_RUBRIC_VERSION || "v1";
const relevant = /data|machine learning|ai|mlops|scientist|engineer/i;
const excluded = /intern|stage|stagiaire|senior|director|head of/i;

const [{ data: cv, error: cvError }, { data: jobs, error: jobsError }] = await Promise.all([
  supabase.from("cv_documents").select("id,content_hash").eq("user_id", userId).eq("is_active", true).maybeSingle(),
  supabase.from("jobs").select("id,title,company_name,description,last_seen_at").eq("is_active", true).eq("description_status", "complete").not("description", "is", null).order("last_seen_at", { ascending: false }).limit(200),
]);
if (cvError) throw new Error(cvError.message);
if (jobsError) throw new Error(jobsError.message);
if (!cv) throw new Error("No active CV found for ATS_AUTO_MATCH_USER_ID.");
const selected = (jobs ?? []).filter((job) => relevant.test(`${job.title} ${job.company_name}`) && !excluded.test(job.title)).slice(0, limit);
for (const job of selected) {
  const inputHash = analysisInputHash(cv.content_hash, job.id, job.description, model, rubric);
  const { error } = await supabase.rpc("enqueue_gemini_analysis_atomic", { p_user_id: userId, p_job_id: job.id, p_cv_document_id: cv.id, p_model_id: model, p_rubric_version: rubric, p_input_hash: inputHash });
  console.log(JSON.stringify({ job_id: job.id, title: job.title, company: job.company_name, queued: !error, error: error?.message ?? null }));
}
console.log(`Selected ${selected.length} job(s); no Gemini API call was made by this command.`);

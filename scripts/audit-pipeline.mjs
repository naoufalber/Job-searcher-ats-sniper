// Read-only hosted/local pipeline diagnostics. Never print credentials or CV text.
import { createRequire } from "node:module";
import { resolve } from "node:path";
const { createClient } = createRequire(resolve("apps/web/package.json"))("@supabase/supabase-js");
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !key) throw new Error("Supabase process credentials are required.");
const db = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
async function read(table, columns) {
  const rows = [];
  for (let offset = 0; ; offset += 500) {
    const { data, error } = await db.from(table).select(columns).range(offset, offset + 499);
    if (error) throw new Error(`${table}: ${error.code}`);
    rows.push(...data);
    if (data.length < 500) return rows;
  }
}
const complete = (text) => !!text && text.trim().length >= 240 && ((text.match(/[.!?]/g) ?? []).length >= 3 || /(responsabil|mission|qualif|requirement|profile|avantage|benefit|skill)/i.test(text));
const [jobs, sources, links, tasks, analyses, cvs, preferences] = await Promise.all([
  read("jobs", "id,title,company_name,description,description_status,first_seen_at,last_seen_at,canonical_url,location,is_active"),
  read("sources", "id,name"), read("job_sources", "job_id,source_id,external_job_id"),
  read("gemini_analysis_queue", "id,job_id,user_id,status,model_id,attempts,next_attempt_at,last_error,updated_at"),
  read("job_analyses", "job_id,status,score,updated_at"),
  read("cv_documents", "user_id,is_active"),
  read("user_preferences", "user_id,target_roles,target_locations,onboarding_completed_at"),
]);
const eligible = preferences.filter(p => p.onboarding_completed_at && cvs.some(c => c.is_active && c.user_id === p.user_id));
const eligibleJobs = jobs.filter(j => j.is_active && complete(j.description) && eligible.some(p =>
  (!p.target_roles.length || p.target_roles.some(r => j.title.toLowerCase().includes(r.toLowerCase()))) &&
  (!p.target_locations.length || !j.location || p.target_locations.some(l => j.location.toLowerCase().includes(l.toLowerCase())))));
const coverage = sources.map(s => {
  const ids = new Set(links.filter(l => l.source_id === s.id).map(l => l.job_id));
  const rows = jobs.filter(j => ids.has(j.id));
  return { source: s.name, total: rows.length, complete: rows.filter(j => complete(j.description)).length };
});
const since = process.argv[2] || new Date(Date.now() - 3600000).toISOString();
console.log(JSON.stringify({ at: new Date().toISOString(), since, host: new URL(url).host,
  counts: { jobs: jobs.length, sources: links.length, complete: jobs.filter(j => complete(j.description)).length, eligibleUsers: eligible.length, eligibleJobs: eligibleJobs.length, tasks: tasks.length }, coverage,
  recentJobs: jobs.filter(j => j.first_seen_at >= since).map(({description, ...j}) => ({...j, descriptionLength: description?.length ?? 0})),
  eligibleExamples: eligibleJobs.slice(0, 5).map(j => ({ id: j.id, company: j.company_name, title: j.title, descriptionLength: j.description.length })),
  tasks: tasks.map(({user_id, ...t}) => t), analyses,
  duplicateCanonicalUrls: jobs.length - new Set(jobs.map(j => j.canonical_url)).size,
}, null, 2));

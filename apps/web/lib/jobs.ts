import { createClient } from "@/lib/supabase/server";
import type { ApplicationStatus, Job, JobStatus } from "@/lib/types";

export type JobListOptions = {
  search?: string;
  source?: string;
  country?: string;
  contractType?: string;
  remoteType?: string;
  sort?: "recent" | "oldest";
  page?: number;
  pageSize?: number;
  view?: "all" | "new";
};

export async function listJobs(options: JobListOptions = {}): Promise<Job[]> {
  const supabase = createClient();
  if (!supabase) return [];
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return [];
  const pageSize = Math.min(Math.max(options.pageSize ?? 24, 1), 50);
  const page = Math.max(options.page ?? 1, 1);
  const from = (page - 1) * pageSize;
  const to = from + pageSize - 1;
  let query = supabase.from("jobs").select("*").eq("is_active", true).order("last_seen_at", { ascending: options.sort === "oldest" }).range(from, to);
  if (options.view === "new") query = query.eq("is_new_since_baseline", true);
  const safeSearch = options.search?.trim().replace(/[(),]/g, " ").slice(0, 80);
  if (safeSearch) query = query.or(`title.ilike.%${safeSearch}%,company_name.ilike.%${safeSearch}%,location.ilike.%${safeSearch}%`);
  if (options.country) query = query.eq("country", options.country);
  if (options.contractType) query = query.eq("contract_type", options.contractType);
  if (options.remoteType) query = query.eq("remote_type", options.remoteType);
  if (options.source) {
    const { data: source } = await supabase.from("sources").select("id").eq("name", options.source).maybeSingle();
    if (!source) return [];
    const { data: links } = await supabase.from("job_sources").select("job_id").eq("source_id", source.id);
    const jobIds = (links ?? []).map((link) => link.job_id);
    if (!jobIds.length) return [];
    query = query.in("id", jobIds);
  }
  const { data } = await query;
  const jobs = (data ?? []) as Job[];
  if (!jobs.length) return jobs;
  const { data: links } = await supabase.from("job_sources").select("job_id, sources(name)").in("job_id", jobs.map((job) => job.id));
  const sourceByJob = new Map<string, string>();
  for (const link of links ?? []) {
    const source = link.sources as unknown as { name?: string } | null;
    if (source?.name) sourceByJob.set(link.job_id as string, source.name);
  }
  const analysisByJob = new Map<string, { status: "pending" | "completed" | "failed"; score: number | null; result: Record<string, unknown> }>();
  const applicationByJob = new Map<string, string>();
  const [{ data: analyses }, { data: statuses }, { data: seenRows }] = await Promise.all([
    supabase.from("job_analyses").select("job_id,status,score,result,updated_at").eq("user_id", auth.user.id).in("job_id", jobs.map((job) => job.id)).order("updated_at", { ascending: false }),
    supabase.from("user_job_status").select("job_id,application_status").eq("user_id", auth.user.id).in("job_id", jobs.map((job) => job.id)),
    supabase.from("user_job_seen").select("job_id,seen_at").eq("user_id", auth.user.id).in("job_id", jobs.map((job) => job.id)),
  ]);
  for (const analysis of analyses ?? []) if (!analysisByJob.has(analysis.job_id as string)) analysisByJob.set(analysis.job_id as string, { status: analysis.status as "pending" | "completed" | "failed", score: analysis.score as number | null, result: (analysis.result ?? {}) as Record<string, unknown> });
  for (const status of statuses ?? []) applicationByJob.set(status.job_id as string, status.application_status as string);
  const seenByJob = new Map<string, string>();
  for (const row of seenRows ?? []) seenByJob.set(row.job_id as string, row.seen_at as string);
  return jobs.map((job) => ({ ...job, source_name: sourceByJob.get(job.id) ?? null, match_score: analysisByJob.get(job.id)?.score ?? null, analysis_status: analysisByJob.get(job.id)?.status ?? null, analysis_result: analysisByJob.get(job.id)?.result ?? null, application_status: applicationByJob.get(job.id) ?? null, seen_at: seenByJob.get(job.id) ?? null }));
}

export async function listSources(): Promise<string[]> {
  const supabase = createClient();
  if (!supabase) return [];
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return [];
  const { data } = await supabase.from("sources").select("name").order("name");
  return (data ?? []).map((source) => source.name as string);
}

export async function getJob(id: string): Promise<Job | null> {
  const supabase = createClient();
  if (!supabase) return null;
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return null;
  const [{ data }, { data: seen }] = await Promise.all([
    supabase.from("jobs").select("*").eq("id", id).maybeSingle(),
    supabase.from("user_job_seen").select("seen_at").eq("user_id", auth.user.id).eq("job_id", id).maybeSingle(),
  ]);
  return data ? ({ ...(data as Job), seen_at: seen?.seen_at ?? null } as Job) : null;
}

export async function getJobsForStatus(status: JobStatus): Promise<Job[]> {
  const supabase = createClient();
  if (!supabase) return [];
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return [];
  const { data } = await supabase.from("user_job_status").select("job_id, jobs(*)").eq("user_id", userData.user.id).eq("status", status);
  return (data ?? []).flatMap((row) => (row.jobs ? [row.jobs as unknown as Job] : []));
}

export async function getApplications(applicationStatus?: ApplicationStatus) {
  const supabase = createClient();
  if (!supabase) return [];
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return [];
  let query = supabase.from("user_job_status").select("job_id,application_status,notes,recruiter_contact,next_follow_up_at,interview_at,applied_at,cv_document_id,jobs(*)").eq("user_id", userData.user.id).order("updated_at", { ascending: false });
  if (applicationStatus) query = query.eq("application_status", applicationStatus);
  const { data } = await query;
  return (data ?? []).flatMap((row) => row.jobs ? [{ ...row, job: row.jobs as unknown as Job }] : []);
}

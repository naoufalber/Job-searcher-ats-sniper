import { createClient } from "@/lib/supabase/server";
import type { Job, JobStatus } from "@/lib/types";

export type JobListOptions = {
  search?: string;
  source?: string;
  country?: string;
  contractType?: string;
  remoteType?: string;
  sort?: "recent" | "oldest";
  page?: number;
  pageSize?: number;
};

export async function listJobs(options: JobListOptions = {}): Promise<Job[]> {
  const supabase = createClient();
  if (!supabase) return [];
  const pageSize = Math.min(Math.max(options.pageSize ?? 24, 1), 50);
  const page = Math.max(options.page ?? 1, 1);
  const from = (page - 1) * pageSize;
  const to = from + pageSize - 1;
  let query = supabase.from("jobs").select("*").eq("is_active", true).order("last_seen_at", { ascending: options.sort === "oldest" }).range(from, to);
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
  return (data ?? []) as Job[];
}

export async function listSources(): Promise<string[]> {
  const supabase = createClient();
  if (!supabase) return [];
  const { data } = await supabase.from("sources").select("name").order("name");
  return (data ?? []).map((source) => source.name as string);
}

export async function getJob(id: string): Promise<Job | null> {
  const supabase = createClient();
  if (!supabase) return null;
  const { data } = await supabase.from("jobs").select("*").eq("id", id).maybeSingle();
  return (data as Job | null) ?? null;
}

export async function getJobsForStatus(status: JobStatus): Promise<Job[]> {
  const supabase = createClient();
  if (!supabase) return [];
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return [];
  const { data } = await supabase.from("user_job_status").select("job_id, jobs(*)").eq("user_id", userData.user.id).eq("status", status);
  return (data ?? []).flatMap((row) => (row.jobs ? [row.jobs as unknown as Job] : []));
}

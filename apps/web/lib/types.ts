export type Job = {
  id: string;
  canonical_url: string;
  company_name: string;
  title: string;
  location: string | null;
  country: string | null;
  contract_type: string | null;
  description: string | null;
  experience_level: string | null;
  remote_type: string | null;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
  metadata?: Record<string, unknown>;
  publication_date?: string | null;
  description_status?: "available" | "missing" | "extraction_failed" | "provider_unavailable" | string | null;
  description_source?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
  required_skills?: string[];
  recruiter_name?: string | null;
  source_name?: string | null;
  match_score?: number | null;
  analysis_status?: "pending" | "completed" | "failed" | null;
  analysis_result?: Record<string, unknown> | null;
  application_status?: string | null;
  is_new_since_baseline?: boolean;
  seen_at?: string | null;
};

export type JobContacts = {
  manager_search_url?: string;
  recruiter_search_url?: string;
};

export type JobStatus = "new" | "saved" | "applied" | "rejected" | "archived";
export type ApplicationStatus = "to_review" | "ready_to_apply" | "applied" | "interview" | "offer" | "rejected" | "withdrawn" | "closed";

export type JobAnalysis = {
  id: string;
  status: "pending" | "completed" | "failed";
  score: number | null;
  result: Record<string, unknown>;
  error_message: string | null;
  updated_at: string;
};

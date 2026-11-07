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
  publication_date?: string | null;
};

export type JobStatus = "new" | "saved" | "applied" | "rejected" | "archived";

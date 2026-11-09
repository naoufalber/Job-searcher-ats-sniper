import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { JobsPagination } from "@/components/jobs-pagination";
import { SeenJobButton } from "@/components/seen-job-button";
import { isDescriptionComplete } from "@/lib/analysis";
import { listJobsPage, listSources } from "@/lib/jobs";
import type { Job } from "@/lib/types";

type Filter = "all" | "high" | "good" | "low" | "pending" | "needs_description" | "saved" | "applied";

function matchesFilter(job: Job, filter: Filter) {
  if (filter === "high") return job.match_score !== null && (job.match_score ?? 0) >= 80;
  if (filter === "good") return job.match_score !== null && (job.match_score ?? 0) >= 65 && (job.match_score ?? 0) < 80;
  if (filter === "low") return job.match_score !== null && (job.match_score ?? 0) < 65;
  if (filter === "pending") return job.analysis_status === "pending";
  if (filter === "needs_description") return !isDescriptionComplete(job.description) && job.description_status !== "complete";
  if (filter === "saved") return job.application_status === "saved";
  if (filter === "applied") return job.application_status === "applied";
  return true;
}

function statusLabel(job: Job) {
  if (job.description_status !== "complete" && !isDescriptionComplete(job.description)) return "Needs description";
  if (job.analysis_status === "completed" && job.match_score !== null) return `Matched - ${job.match_score}/100`;
  if (job.analysis_status === "pending") return "To review";
  if (job.analysis_status === "failed") return "Analysis failed";
  return "To review";
}

function contactUrl(value: unknown) {
  return typeof value === "string" && /^https?:\/\//i.test(value) ? value : null;
}

function contactLinks(job: Job) {
  const contacts = job.metadata?.contacts;
  if (!contacts || typeof contacts !== "object") return [];
  const values = contacts as { manager_search_url?: unknown; recruiter_search_url?: unknown };
  return [["Manager search", contactUrl(values.manager_search_url)], ["Recruiter search", contactUrl(values.recruiter_search_url)]]
    .filter((entry): entry is [string, string] => Boolean(entry[1]));
}

export default async function JobsPage({ searchParams }: { searchParams: { q?: string; source?: string; country?: string; contract?: string; remote?: string; sort?: "recent" | "oldest" | "company" | "score"; filter?: Filter; view?: "new" | "all"; page?: string } }) {
  const search = searchParams.q ?? "";
  const page = Math.max(Number.parseInt(searchParams.page ?? "1", 10) || 1, 1);
  const filter = searchParams.filter ?? "all";
  const view: "new" | "all" = searchParams.view === "all" ? "all" : "new";
  const pageSize = 50;
  const filters = { search, source: searchParams.source, country: searchParams.country, contractType: searchParams.contract, remoteType: searchParams.remote, sort: searchParams.sort === "oldest" ? ("oldest" as const) : ("recent" as const), page, pageSize, view };
  const [{ jobs: rawJobs, total }, sources] = await Promise.all([listJobsPage(filters), listSources()]);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const jobs = rawJobs.filter((job) => matchesFilter(job, filter)).sort((a, b) => {
    if (searchParams.sort === "company") return a.company_name.localeCompare(b.company_name);
    if (searchParams.sort === "score") return (b.match_score ?? -1) - (a.match_score ?? -1);
    if (a.match_score !== null && b.match_score !== null) return (b.match_score ?? 0) - (a.match_score ?? 0);
    if (a.match_score !== null) return -1;
    if (b.match_score !== null) return 1;
    return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime();
  });
  const query = new URLSearchParams({ q: search, source: searchParams.source ?? "", country: searchParams.country ?? "", contract: searchParams.contract ?? "", remote: searchParams.remote ?? "", sort: searchParams.sort ?? "recent", filter, view });
  const hrefBase = `/jobs?${query.toString()}`;
  const nextHref = `${hrefBase}&page=${Math.min(page + 1, totalPages)}`;
  const previousHref = `${hrefBase}&page=${Math.max(page - 1, 1)}`;

  return <div className="mx-auto max-w-7xl px-6 py-12 lg:px-10">
    <div className="border-b border-line pb-8"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Discovery</p><h1 className="mt-2 text-4xl font-semibold tracking-tight text-ink">Open roles</h1><p className="mt-3 text-slate-500">{view === "new" ? "New roles discovered since staging activation." : "All collected roles, including historical roles for onboarding and backfill."}</p>
      <form className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6" method="get"><input className="focus-ring rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none placeholder:text-slate-400 lg:col-span-2" name="q" defaultValue={search} placeholder="Title, company, or location" /><select className="focus-ring rounded-xl border border-line bg-white px-3 py-3 text-sm" name="source" defaultValue={searchParams.source ?? ""}><option value="">All sources</option>{sources.map((source) => <option key={source} value={source}>{source}</option>)}</select><input className="focus-ring rounded-xl border border-line bg-white px-4 py-3 text-sm" name="country" defaultValue={searchParams.country ?? ""} placeholder="Country" /><input className="focus-ring rounded-xl border border-line bg-white px-4 py-3 text-sm" name="contract" defaultValue={searchParams.contract ?? ""} placeholder="Contract type" /><select className="focus-ring rounded-xl border border-line bg-white px-3 py-3 text-sm" name="view" defaultValue={view}><option value="new">New jobs</option><option value="all">All jobs</option></select><select className="focus-ring rounded-xl border border-line bg-white px-3 py-3 text-sm" name="filter" defaultValue={filter}><option value="all">All statuses</option><option value="high">High match (80+)</option><option value="good">Good match (65-79)</option><option value="low">Low match (&lt;65)</option><option value="pending">Pending analysis</option><option value="needs_description">Needs description</option><option value="saved">Saved</option><option value="applied">Applied</option></select><div className="flex gap-2 lg:col-span-6"><select className="focus-ring rounded-xl border border-line bg-white px-3 py-3 text-sm" name="sort" defaultValue={searchParams.sort ?? "recent"}><option value="recent">Recommended order</option><option value="score">Match score</option><option value="oldest">Date discovered</option><option value="company">Company</option></select><button className="focus-ring rounded-xl bg-moss px-5 py-3 text-sm font-semibold text-white" type="submit">Apply filters</button></div></form>
    </div>
    <div id="jobs-table" className="scroll-mt-6 mt-8 overflow-x-auto rounded-2xl border border-line bg-white"><table className="min-w-[980px] w-full text-left text-sm"><thead className="border-b border-line bg-paper text-xs uppercase tracking-[0.12em] text-slate-500"><tr><th className="px-5 py-4">Job title</th><th className="px-5 py-4">Company</th><th className="px-5 py-4">Location</th><th className="px-5 py-4">Source</th><th className="px-5 py-4">First seen</th><th className="px-5 py-4">Contract</th><th className="px-5 py-4">CV match</th><th className="px-5 py-4">Contacts</th><th className="px-5 py-4">Status</th><th className="px-5 py-4">Action</th></tr></thead><tbody className="divide-y divide-line">{jobs.map((job) => <tr key={job.id} className="align-top"><td className="px-5 py-4 font-semibold text-ink"><div className="flex flex-wrap items-center gap-2"><Link className="hover:text-moss hover:underline" href={`/jobs/${job.id}`}>{job.title}</Link>{job.is_new_since_baseline && <span className="rounded-full bg-moss/10 px-2 py-1 text-xs font-semibold text-moss">New</span>}</div></td><td className="px-5 py-4 text-slate-700">{job.company_name}</td><td className="px-5 py-4 text-slate-600">{job.location ?? "Not listed"}</td><td className="px-5 py-4 text-slate-600">{job.source_name ?? "Unknown"}</td><td className="px-5 py-4 text-slate-600"><time dateTime={job.first_seen_at}>{new Date(job.first_seen_at).toLocaleString()}</time></td><td className="px-5 py-4 text-slate-600">{job.contract_type ?? "Not listed"}</td><td className="px-5 py-4 font-semibold text-moss">{job.match_score === null || job.match_score === undefined ? "-" : `${job.match_score}/100`}</td><td className="px-5 py-4 text-slate-600"><div className="flex flex-col gap-1">{contactLinks(job).length ? contactLinks(job).map(([label, href]) => <a key={label} className="text-moss underline hover:text-ink" href={href} target="_blank" rel="noreferrer">{label}</a>) : "Not listed"}</div></td><td className="px-5 py-4"><span className="rounded-full bg-paper px-3 py-1 text-xs text-slate-700">{statusLabel(job)}</span></td><td className="px-5 py-4"><Link className="font-semibold text-moss hover:underline" href={`/jobs/${job.id}`}>View role</Link><SeenJobButton jobId={job.id} seenAt={job.seen_at} /></td></tr>)}</tbody></table>{!jobs.length && <div className="p-8"><EmptyState title={view === "new" ? "No new roles yet" : "No matching roles"} body={view === "new" ? "Switch to All jobs to browse historical roles, or wait for the next collector run." : "Try broader filters or wait for the next collector run."} /></div>}</div>
    <JobsPagination currentPage={Math.min(page, totalPages)} totalPages={totalPages} previousHref={previousHref} nextHref={nextHref} hrefBase={hrefBase} />
  </div>;
}

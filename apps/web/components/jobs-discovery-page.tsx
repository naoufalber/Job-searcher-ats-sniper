import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { JobsPagination } from "@/components/jobs-pagination";
import { JobsLiveUpdates } from "@/components/jobs-live-updates";
import { SeenJobButton } from "@/components/seen-job-button";
import { isDescriptionComplete } from "@/lib/analysis";
import { getMatchingProviderStatus, listJobsPage, listSources } from "@/lib/jobs";
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
  if (job.analysis_status === "completed" && job.match_score !== null) return "To review";
  if (job.matching_status === "processing") return "Matching CV";
  if (job.matching_status === "pending" && /quota|rate limit/i.test(job.matching_error ?? "")) return "Waiting for Gemini quota";
  if (job.analysis_status === "pending" || job.matching_status === "pending") return "Queued for matching";
  if (job.analysis_status === "failed") return "Analysis failed";
  return "Awaiting matching";
}

function contactUrl(value: unknown) {
  return typeof value === "string" && /^https?:\/\//i.test(value) ? value : null;
}

function descriptionIssue(job: Job) {
  if (job.description_status === "complete" || isDescriptionComplete(job.description)) return null;
  const extraction = job.metadata?.description_extraction as { reason?: unknown } | undefined;
  return typeof extraction?.reason === "string" ? extraction.reason.slice(0, 200) : "Extraction details not yet recorded.";
}

function contactLinks(job: Job) {
  const contacts = job.metadata?.contacts;
  if (!contacts || typeof contacts !== "object") return [];
  const values = contacts as { manager_search_url?: unknown; recruiter_search_url?: unknown };
  return [["Manager search", contactUrl(values.manager_search_url)], ["Recruiter search", contactUrl(values.recruiter_search_url)]]
    .filter((entry): entry is [string, string] => Boolean(entry[1]));
}

export type JobsSearchParams = { q?: string; source?: string; country?: string; contract?: string; remote?: string; sort?: "recent" | "oldest" | "newest" | "company" | "score"; filter?: Filter; view?: "new" | "all"; page?: string };

export default async function JobsDiscoveryPage({ searchParams, explore = false }: { searchParams: JobsSearchParams; explore?: boolean }) {
  const search = searchParams.q ?? "";
  const page = Math.max(Number.parseInt(searchParams.page ?? "1", 10) || 1, 1);
  const filter = explore || searchParams.filter === "needs_description" ? "all" : searchParams.filter ?? "all";
  const view: "new" | "all" = searchParams.view === "all" ? "all" : "new";
  const pageSize = 50;
  const filters = { search, source: searchParams.source, country: searchParams.country, contractType: searchParams.contract, remoteType: searchParams.remote, sort: searchParams.sort === "newest" ? ("newest" as const) : searchParams.sort === "oldest" ? ("oldest" as const) : ("recent" as const), page, pageSize, view };
  const [{ jobs: rawJobs, total }, sources, providerStatus] = await Promise.all([listJobsPage({ ...filters, descriptionView: explore ? "missing" : "ready" }), listSources(), explore ? null : getMatchingProviderStatus()]);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const jobs = rawJobs.filter((job) => matchesFilter(job, filter)).sort((a, b) => {
    if (searchParams.sort === "newest") return new Date(b.first_seen_at).getTime() - new Date(a.first_seen_at).getTime();
    if (searchParams.sort === "company") return a.company_name.localeCompare(b.company_name);
    if (searchParams.sort === "score") return (b.match_score ?? -1) - (a.match_score ?? -1);
    if (a.match_score !== null && b.match_score !== null) return (b.match_score ?? 0) - (a.match_score ?? 0);
    if (a.match_score !== null) return -1;
    if (b.match_score !== null) return 1;
    return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime();
  });
  const query = new URLSearchParams({ q: search, source: searchParams.source ?? "", country: searchParams.country ?? "", contract: searchParams.contract ?? "", remote: searchParams.remote ?? "", sort: searchParams.sort ?? "recent", filter, view });
  const hrefBase = `${explore ? "/jobs/explore" : "/jobs"}?${query.toString()}`;
  const nextHref = `${hrefBase}&page=${Math.min(page + 1, totalPages)}`;
  const previousHref = `${hrefBase}&page=${Math.max(page - 1, 1)}`;

  return <div className="mx-auto max-w-7xl px-6 py-12 lg:px-10">
    <JobsLiveUpdates />
    {providerStatus && <div className="mb-5 mt-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900" role="status"><p>Gemini is currently rate-limiting matching. Your jobs are saved and will retry automatically.</p><p className="mt-1 text-xs">{providerStatus.reason} Next quota check: {new Date(providerStatus.blocked_until).toLocaleString("en-GB", { timeZone: "Europe/Paris" })} (Paris time).</p></div>}
    <div className="border-b border-line pb-8"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Discovery</p><h1 className="mt-2 text-4xl font-semibold tracking-tight text-ink">{explore ? "Explore more" : "Open roles"}</h1><p className="mt-3 text-slate-500">{explore ? "Offers awaiting a complete description. Browse the original listing while extraction is retried." : "Roles with complete descriptions, ready for CV matching and review."}</p>
      <div className="mt-5 flex flex-wrap items-center gap-3 text-sm"><Link className={`focus-ring rounded-full px-4 py-2 ${explore ? "text-slate-500 hover:text-moss" : "bg-moss text-white"}`} href={`/jobs?${query.toString()}`} aria-current={!explore ? "page" : undefined}>Discover</Link><Link className={`focus-ring rounded-full px-4 py-2 ${explore ? "bg-moss text-white" : "text-slate-500 hover:text-moss"}`} href={`/jobs/explore?${query.toString()}`} aria-current={explore ? "page" : undefined}>Explore more</Link><span className="text-xs text-slate-500">{total} {total === 1 ? "offer" : "offers"}</span></div><form className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6" method="get"><input type="hidden" name="remote" value={searchParams.remote ?? ""} /><input className="focus-ring rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none placeholder:text-slate-400 lg:col-span-2" name="q" defaultValue={search} placeholder="Title, company, or location" /><select className="focus-ring rounded-xl border border-line bg-white px-3 py-3 text-sm" name="source" defaultValue={searchParams.source ?? ""}><option value="">All sources</option>{sources.map((source) => <option key={source} value={source}>{source}</option>)}</select><input className="focus-ring rounded-xl border border-line bg-white px-4 py-3 text-sm" name="country" defaultValue={searchParams.country ?? ""} placeholder="Country" /><input className="focus-ring rounded-xl border border-line bg-white px-4 py-3 text-sm" name="contract" defaultValue={searchParams.contract ?? ""} placeholder="Contract type" /><select className="focus-ring rounded-xl border border-line bg-white px-3 py-3 text-sm" name="view" defaultValue={view}><option value="new">New jobs</option><option value="all">All jobs</option></select>{!explore && <select className="focus-ring rounded-xl border border-line bg-white px-3 py-3 text-sm" name="filter" defaultValue={filter}><option value="all">All statuses</option><option value="high">High match (80+)</option><option value="good">Good match (65-79)</option><option value="low">Low match (&lt;65)</option><option value="pending">Pending analysis</option><option value="saved">Saved</option><option value="applied">Applied</option></select>}<div className="flex gap-2 lg:col-span-6"><select className="focus-ring rounded-xl border border-line bg-white px-3 py-3 text-sm" name="sort" defaultValue={searchParams.sort ?? "recent"}><option value="recent">Recommended order</option><option value="newest">Newest first</option><option value="score">Match score</option><option value="oldest">Date discovered</option><option value="company">Company</option></select><button className="focus-ring rounded-xl bg-moss px-5 py-3 text-sm font-semibold text-white" type="submit">Apply filters</button></div></form>
    </div>
    <div id="jobs-table" className="scroll-mt-6 mt-8 overflow-x-auto rounded-2xl border border-line bg-white"><table className="min-w-[980px] w-full text-left text-sm"><thead className="border-b border-line bg-paper text-xs uppercase tracking-[0.12em] text-slate-500"><tr><th className="px-5 py-4">Job title</th><th className="px-5 py-4">Company</th><th className="px-5 py-4">Location</th><th className="px-5 py-4">Source</th><th className="px-5 py-4">First seen</th><th className="px-5 py-4">Contract</th>{!explore && <th className="px-5 py-4">CV match</th>}<th className="px-5 py-4">Contacts</th><th className="px-5 py-4">Status</th><th className="px-5 py-4">Action</th></tr></thead><tbody className="divide-y divide-line">{jobs.map((job) => <tr key={job.id} className="align-top"><td className="px-5 py-4 font-semibold text-ink"><div className="flex flex-wrap items-center gap-2"><Link className="hover:text-moss hover:underline" href={`/jobs/${job.id}`}>{job.title}</Link>{job.is_new_since_baseline && <span className="rounded-full bg-moss/10 px-2 py-1 text-xs font-semibold text-moss">New</span>}</div></td><td className="px-5 py-4 text-slate-700">{job.company_name}</td><td className="px-5 py-4 text-slate-600">{job.location ?? "Not listed"}</td><td className="px-5 py-4 text-slate-600">{job.source_name ?? "Unknown"}</td><td className="px-5 py-4 text-slate-600"><time dateTime={job.first_seen_at}>{new Date(job.first_seen_at).toLocaleString()}</time></td><td className="px-5 py-4 text-slate-600">{job.contract_type ?? (typeof job.analysis_result?.contract_type === "string" ? <span title={typeof job.analysis_result.contract_evidence === "string" ? `Extracted by AI: ${job.analysis_result.contract_evidence}` : "Extracted by AI from the job listing"}>{job.analysis_result.contract_type}</span> : "Not listed")}</td>{!explore && <td className="px-5 py-4 font-semibold text-moss">{job.match_score === null || job.match_score === undefined ? statusLabel(job) : `${job.match_score}/100`}</td>}<td className="px-5 py-4 text-slate-600"><div className="flex flex-col gap-1">{contactLinks(job).length ? contactLinks(job).map(([label, href]) => <a key={label} className="text-moss underline hover:text-ink" href={href} target="_blank" rel="noreferrer">{label}</a>) : "Not listed"}</div></td><td className="px-5 py-4"><span className="rounded-full bg-paper px-3 py-1 text-xs text-slate-700">{statusLabel(job)}</span>{job.matching_error && <p className="mt-2 max-w-48 text-xs leading-relaxed text-slate-500">{job.matching_error}</p>}{descriptionIssue(job) && <p className="mt-2 max-w-48 text-xs leading-relaxed text-slate-500">{descriptionIssue(job)}</p>}</td><td className="px-5 py-4"><Link className="font-semibold text-moss hover:underline" href={`/jobs/${job.id}`}>View role</Link><SeenJobButton jobId={job.id} seenAt={job.seen_at} /></td></tr>)}</tbody></table>{!jobs.length && <div className="p-8"><EmptyState title={explore ? "No offers awaiting descriptions" : "No matching roles"} body={explore ? "Try broader filters or return to Discover for roles ready to review." : "Try All jobs or broader filters. Offers without complete descriptions are in Explore more."} /></div>}</div>
    <JobsPagination currentPage={Math.min(page, totalPages)} totalPages={totalPages} previousHref={previousHref} nextHref={nextHref} hrefBase={hrefBase} />
  </div>;
}

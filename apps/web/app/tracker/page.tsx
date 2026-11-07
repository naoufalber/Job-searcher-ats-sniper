import { EmptyState } from "@/components/empty-state";
import { JobCard } from "@/components/job-card";
import { getJobsForStatus } from "@/lib/jobs";

export default async function TrackerPage() { const jobs = await getJobsForStatus("applied"); return <div className="mx-auto max-w-7xl px-6 py-12 lg:px-10"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Application tracker</p><h1 className="mt-2 text-4xl font-semibold tracking-tight text-ink">Your pipeline</h1><p className="mt-3 text-slate-500">Keep the collection feed separate from your personal application workflow.</p><div className="mt-8">{jobs.length ? <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">{jobs.map((job) => <JobCard key={job.id} job={job} />)}</div> : <EmptyState title="Your pipeline is clear" body="Applied roles will appear here once the authenticated tracker actions are enabled." />}</div></div>; }

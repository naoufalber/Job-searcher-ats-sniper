import { EmptyState } from "@/components/empty-state";
import { JobCard } from "@/components/job-card";
import { getJobsForStatus } from "@/lib/jobs";

export default async function SavedPage() { const jobs = await getJobsForStatus("saved"); return <div className="mx-auto max-w-7xl px-6 py-12 lg:px-10"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Your shortlist</p><h1 className="mt-2 text-4xl font-semibold tracking-tight text-ink">Saved roles</h1><div className="mt-8">{jobs.length ? <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">{jobs.map((job) => <JobCard key={job.id} job={job} />)}</div> : <EmptyState title="Nothing saved yet" body="Sign in and save roles from the discovery feed when the tracker actions are connected." />}</div></div>; }

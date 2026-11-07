import Link from "next/link";
import { notFound } from "next/navigation";
import { getJob } from "@/lib/jobs";
import { StatusActions } from "@/components/status-actions";

export default async function JobDetailPage({ params }: { params: { id: string } }) {
  const job = await getJob(params.id);
  if (!job) notFound();
  return <div className="mx-auto max-w-4xl px-6 py-12 lg:px-10"><Link className="focus-ring rounded text-sm font-semibold text-moss hover:underline" href="/jobs">← Back to discovery</Link><article className="mt-10 rounded-3xl border border-line bg-white p-7 md:p-10"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">{job.company_name}</p><h1 className="mt-3 text-4xl font-semibold tracking-tight text-ink">{job.title}</h1><div className="mt-5 flex flex-wrap gap-2 text-sm text-slate-500"><span className="rounded-full bg-paper px-3 py-1">{job.location ?? "Location not listed"}</span>{job.remote_type && <span className="rounded-full bg-paper px-3 py-1">{job.remote_type}</span>}{job.experience_level && <span className="rounded-full bg-paper px-3 py-1">{job.experience_level}</span>}</div><StatusActions jobId={job.id} /><div className="mt-10 border-t border-line pt-8"><h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-500">Description</h2>{job.description ? <div className="mt-4 whitespace-pre-wrap text-[15px] leading-8 text-slate-700">{job.description}</div> : <p className="mt-4 text-slate-500">No description was provided by the source. Open the original listing for the canonical details.</p>}</div><a className="focus-ring mt-10 inline-flex rounded-full bg-moss px-5 py-3 text-sm font-semibold text-white" href={job.canonical_url} target="_blank" rel="noreferrer">Open original listing ↗</a></article></div>;
}

import JobsDiscoveryPage, { type JobsSearchParams } from "@/components/jobs-discovery-page";

export default function JobsPage({ searchParams }: { searchParams: JobsSearchParams }) {
  return <JobsDiscoveryPage searchParams={searchParams} />;
}

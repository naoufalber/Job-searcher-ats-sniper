import JobsDiscoveryPage, { type JobsSearchParams } from "@/components/jobs-discovery-page";

export default function ExploreJobsPage({ searchParams }: { searchParams: JobsSearchParams }) {
  return <JobsDiscoveryPage searchParams={searchParams} explore />;
}

import { createHash } from "node:crypto";

// Match enqueue_matching_for_job's md5(jsonb_build_object(...)::text).
// PostgreSQL JSONB orders these fixed string keys by byte length, then bytes.
export function analysisInputHash(cvHash, jobId, description, model, rubric) {
  const fields = { cv: cvHash, job: jobId, model, rubric, description };
  const text = `{${Object.entries(fields).map(([key, value]) => `${JSON.stringify(key)}: ${JSON.stringify(value)}`).join(", ")}}`;
  return createHash("md5").update(text).digest("hex");
}

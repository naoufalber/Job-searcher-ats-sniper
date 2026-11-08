import { createHash } from "node:crypto";

export function isDescriptionComplete(description: string | null | undefined) {
  if (!description || description.trim().length < 240) return false;
  const signals = /(responsabil|mission|qualif|requirement|profile|avantage|benefit|skill)/i;
  return (description.match(/[.!?]/g) ?? []).length >= 3 || signals.test(description);
}

export function analysisInputHash(cvHash: string, jobId: string, description: string, model: string, rubric: string) {
  return createHash("sha256").update(JSON.stringify({ cv: cvHash, job: jobId, description, model, rubric })).digest("hex");
}

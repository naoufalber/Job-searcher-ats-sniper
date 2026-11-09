export { analysisInputHash } from "./matching-input.mjs";

export function isDescriptionComplete(description: string | null | undefined) {
  if (!description || description.trim().length < 240) return false;
  const signals = /(responsabil|mission|qualif|requirement|profile|avantage|benefit|skill)/i;
  return (description.match(/[.!?]/g) ?? []).length >= 3 || signals.test(description);
}

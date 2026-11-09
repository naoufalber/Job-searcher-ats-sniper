export function nextPermittedTime(attempts, nowMs, limit = 10, windowMs = 60_000) {
  const recent = attempts.filter((timestamp) => timestamp > nowMs - windowMs).sort((a, b) => a - b);
  if (recent.length < limit) return nowMs;
  return recent[recent.length - limit] + windowMs;
}

export function retryDelayMs(attempt, retryAfterMs, random = 0.5) {
  if (retryAfterMs != null) return Math.max(1_000, Math.min(900_000, retryAfterMs));
  const base = Math.min(300_000, 2 ** Math.max(0, attempt - 1) * 1_000);
  return base + Math.floor(Math.max(0, Math.min(1, random)) * 500);
}

export function providerQuotaGuidance(payload, retryAfter, now = Date.now()) {
  const details = Array.isArray(payload?.error?.details) ? payload.error.details : [];
  const violations = details.flatMap(d => Array.isArray(d.violations) ? d.violations : []);
  const ids = violations.map(v => v.quotaId || v.quotaMetric).filter(v => typeof v === "string").map(v => v.replace(/[^a-zA-Z0-9_./-]/g, "").slice(0, 160));
  const daily = ids.some(id => /perday|per_day|daily/i.test(id));
  const retryInfo = details.find(d => typeof d.retryDelay === "string");
  const seconds = Number.parseFloat(retryInfo?.retryDelay ?? "");
  const headerSeconds = Number(retryAfter);
  const headerDate = retryAfter ? Date.parse(retryAfter) : NaN;
  const headerMs = retryAfter == null ? 0 : Number.isFinite(headerSeconds) ? headerSeconds * 1000 : Number.isFinite(headerDate) ? headerDate - now : 0;
  const guidedWait = Math.max(Number.isFinite(seconds) ? seconds * 1000 : 0, headerMs);
  // Honor a supplied retry deadline; otherwise avoid guessing the daily reset.
  const waitMs = Math.max(1000, guidedWait || (daily ? 3600000 : 60000));
  const limits = violations.map(v => String(v.quotaValue ?? "")).filter(v => /^\d+$/.test(v));
  return { waitMs, quotaIds: ids, limits, reason: `Gemini ${daily ? "daily " : ""}quota exhausted${ids.length ? ` (${ids.join(", ")})` : ""}${limits.length ? `; provider limit: ${limits.join(", ")}` : ""}.` };
}

export function nextPermittedTime(attempts, nowMs, limit = 14, windowMs = 60_000) {
  const recent = attempts.filter((timestamp) => timestamp > nowMs - windowMs).sort((a, b) => a - b);
  if (recent.length < limit) return nowMs;
  return recent[recent.length - limit] + windowMs;
}

export function retryDelayMs(attempt, retryAfterMs, random = 0.5) {
  if (retryAfterMs != null) return Math.max(1_000, Math.min(900_000, retryAfterMs));
  const base = Math.min(300_000, 2 ** Math.max(0, attempt - 1) * 1_000);
  return base + Math.floor(Math.max(0, Math.min(1, random)) * 500);
}

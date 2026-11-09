import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { nextPermittedTime, retryDelayMs } from "../../../scripts/gemini-rate-limit.mjs";

describe("Gemini rolling-window policy", () => {
  it("allows ten attempts and waits only for the earliest slot on the eleventh", () => {
    const now = 1_000_000;
    const timestamps = Array.from({ length: 10 }, (_, index) => now - 59_000 + index * 100);
    assert.equal(nextPermittedTime(timestamps, now), timestamps[0] + 60_000);
    assert.equal(nextPermittedTime(timestamps.slice(0, 9), now), now);
  });

  it("handles concurrent reservations deterministically when timestamps are serialized", () => {
    const now = 2_000_000;
    const timestamps = Array.from({ length: 8 }, (_, index) => now - 1_000 - index);
    const first = nextPermittedTime(timestamps, now);
    assert.equal(first, now);
    timestamps.push(now);
    assert.equal(nextPermittedTime(timestamps, now), now);
    timestamps.push(now);
    assert.ok(nextPermittedTime(timestamps, now) > now);
  });

  it("honors provider retry guidance and bounds exponential backoff", () => {
    assert.equal(retryDelayMs(1, 12_000), 12_000);
    assert.equal(retryDelayMs(20, null, 1), 300_500);
  });

  it("does not include credentials in policy outputs", () => {
    assert.equal(JSON.stringify({ rpm: 14, next: nextPermittedTime([], 10) }).includes("GEMINI_API_KEY"), false);
  });
});

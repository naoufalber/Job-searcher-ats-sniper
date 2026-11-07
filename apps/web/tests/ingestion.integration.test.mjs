import assert from "node:assert/strict";
import { describe, it } from "node:test";

const baseUrl = process.env.LOCAL_WEB_URL ?? "http://127.0.0.1:3000";
const secret = process.env.LOCAL_INGESTION_SECRET;
if (!secret) throw new Error("LOCAL_INGESTION_SECRET is required for local ingestion tests.");
if (!/^https?:\/\/127\.0\.0\.1(?::\d+)?$/.test(baseUrl) && !/^https?:\/\/localhost(?::\d+)?$/.test(baseUrl)) {
  throw new Error(`Refusing to run ingestion tests against non-local URL: ${baseUrl}`);
}

const payload = {
  source: "local-integration",
  external_job_id: `local-${Date.now()}`,
  company_name: "Local Integration Co",
  title: "Data Engineer (integration fixture)",
  location: "Paris, France",
  country: "France",
  contract_type: "full_time",
  remote_type: "hybrid",
  canonical_url: `https://example.invalid/jobs/${Date.now()}`,
  description: "Integration fixture only.",
  metadata: { test: true },
};

async function post(body, providedSecret = secret) {
  return fetch(`${baseUrl}/api/ingest/jobs`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-ats-ingestion-secret": providedSecret },
    body: JSON.stringify(body),
  });
}

function variant(overrides) {
  return { ...payload, ...overrides };
}

describe("local ingestion API", { concurrency: 1 }, () => {
  it("rejects unauthorized requests", async () => {
    const response = await post(payload, "wrong-secret");
    assert.equal(response.status, 401);
  });

  it("rejects invalid payloads", async () => {
    const response = await post({ ...payload, canonical_url: "not-a-url" });
    assert.equal(response.status, 422);
  });

  it("accepts idempotent job ingestion", async () => {
    const first = await post(payload);
    const firstText = await first.text();
    assert.equal(first.status, 200, firstText);
    const firstBody = JSON.parse(firstText);
    const second = await post(payload);
    const secondText = await second.text();
    assert.equal(second.status, 200, secondText);
    const secondBody = JSON.parse(secondText);
    assert.equal(secondBody.job_id, firstBody.job_id);
    assert.equal(secondBody.source_id, firstBody.source_id);
  });

  it("is idempotent for concurrent requests", async () => {
    const concurrentPayload = variant({
      external_job_id: `concurrent-${Date.now()}`,
      canonical_url: `https://example.invalid/jobs/concurrent-${Date.now()}`,
    });
    const responses = await Promise.all([post(concurrentPayload), post(concurrentPayload)]);
    const bodies = await Promise.all(responses.map(async (response) => {
      const text = await response.text();
      assert.equal(response.status, 200, text);
      return JSON.parse(text);
    }));
    assert.equal(bodies[0].job_id, bodies[1].job_id);
    assert.equal(bodies[0].source_id, bodies[1].source_id);
  });

  it("keeps one job when a provider changes its canonical URL", async () => {
    const externalJobId = `changed-url-${Date.now()}`;
    const first = await post(variant({
      external_job_id: externalJobId,
      canonical_url: `https://example.invalid/jobs/old-${Date.now()}`,
    }));
    const firstText = await first.text();
    assert.equal(first.status, 200, firstText);
    const firstBody = JSON.parse(firstText);
    const second = await post(variant({
      external_job_id: externalJobId,
      canonical_url: `https://example.invalid/jobs/new-${Date.now()}`,
    }));
    const secondText = await second.text();
    assert.equal(second.status, 200, secondText);
    const secondBody = JSON.parse(secondText);
    assert.equal(secondBody.job_id, firstBody.job_id);
    assert.equal(secondBody.source_id, firstBody.source_id);
  });
});

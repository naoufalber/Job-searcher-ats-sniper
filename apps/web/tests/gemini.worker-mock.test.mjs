import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { requestGemini, analysisResponseSchema } from "../../../scripts/gemini-provider.mjs";

const result = JSON.stringify({ score: 80, confidence: "high", matching_skills: [], missing_required_skills: [], experience_gaps: [], education_gaps: [], language_location_considerations: [], explanation: "mock", cv_adaptation_suggestions: [], recommended_action: "Apply" });

describe("Gemini worker provider boundary", () => {
  it("uses the mock response without invoking fetch", async () => {
    let called = false;
    const response = await requestGemini({ useMock: true, mockResponse: result, modelId: "invalid-model", prompt: "ignored", apiKey: "not-used", fetchImpl: async () => { called = true; throw new Error("network must not be called"); } });
    assert.equal(called, false);
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.candidates[0].content.parts[0].text, result);
  });

  it("uses fetch only in provider mode", async () => {
    let calledUrl = "";
    const response = await requestGemini({ useMock: false, modelId: "gemini-test", prompt: "safe", apiKey: "key", fetchImpl: async (url) => { calledUrl = url; return new Response("{}", { status: 200 }); } });
    assert.match(calledUrl, /generativelanguage\.googleapis\.com/);
    assert.equal(response.status, 200);
  });

  it("requires the complete analysis contract in provider generation", async () => {
    let body;
    await requestGemini({ useMock: false, modelId: "gemini-test", prompt: "safe", apiKey: "test", fetchImpl: async (_url, options) => {
      body = JSON.parse(options.body);
      return new Response("{}", { status: 200 });
    } });
    assert.deepEqual(body.generationConfig.responseSchema, analysisResponseSchema);
    assert.deepEqual(analysisResponseSchema.required.sort(), Object.keys(JSON.parse(result)).sort());
    assert.equal(analysisResponseSchema.properties.score.maximum, 100);
    assert.deepEqual(analysisResponseSchema.properties.recommended_action.enum, ["Apply", "Review", "Low priority"]);
  });
});

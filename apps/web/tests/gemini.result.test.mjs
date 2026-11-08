import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { normalizeAnalysis, parseAnalysisResponse } from "../../../scripts/gemini-result.mjs";

const valid = {
  score: 82,
  confidence: "high",
  matching_skills: [{ skill: "Python", evidence: "The CV lists Python projects." }],
  missing_required_skills: ["Kubernetes"],
  experience_gaps: [],
  education_gaps: [],
  language_location_considerations: [],
  explanation: "Strong overlap in data engineering and Python experience.",
  cv_adaptation_suggestions: ["Highlight production data pipelines."],
  recommended_action: "Apply",
};

describe("Gemini result normalization", () => {
  it("accepts JSON wrapped in a markdown fence and preserves the contract", () => {
    const result = parseAnalysisResponse(`Here is the result:\n\`\`\`json\n${JSON.stringify(valid)}\n\`\`\``);
    assert.deepEqual(result, valid);
  });

  it("normalizes common model aliases without inventing evidence", () => {
    const result = normalizeAnalysis({ ...valid, score: "75", matching_skills: ["Python"], missing_required_skills: undefined, missing_skills: ["Airflow"], recommended_action: undefined, recommendation: "review", summary: valid.explanation, explanation: undefined });
    assert.equal(result?.score, 75);
    assert.deepEqual(result?.matching_skills, [{ skill: "Python", evidence: "" }]);
    assert.deepEqual(result?.missing_required_skills, ["Airflow"]);
    assert.equal(result?.recommended_action, "Review");
  });

  it("rejects incomplete or unsafe results", () => {
    assert.equal(parseAnalysisResponse("not json"), null);
    assert.equal(normalizeAnalysis({ ...valid, score: 101 }), null);
  });
});

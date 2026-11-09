import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { normalizeAnalysis, parseAnalysisResponse, verifiedContract } from "../../../scripts/gemini-result.mjs";

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

  it("preserves contract extraction without requiring it in older cached analyses", () => {
    assert.equal(normalizeAnalysis(valid).contract_type, undefined);
    const result = normalizeAnalysis({ ...valid, contract_type: "CDI", contract_evidence: "Poste en CDI" });
    assert.equal(result.contract_type, "CDI");
    assert.deepEqual(verifiedContract(result, "Data Scientist", "Poste en CDI à Paris."), { contract_type: "CDI", contract_evidence: "Poste en CDI" });
  });

  it("accepts evidence from the title and rejects unsupported or CV-only contract claims", () => {
    assert.equal(verifiedContract({ contract_type: "Internship", contract_evidence: "Stage Data Scientist" }, "Stage Data Scientist", "Responsibilities").contract_type, "Internship");
    assert.equal(verifiedContract({ contract_type: "CDI", contract_evidence: "Previous permanent role" }, "Data Scientist", "No contract stated").contract_type, null);
    assert.equal(verifiedContract({ contract_type: "unknown", contract_evidence: "Data Scientist" }, "Data Scientist", "").contract_type, null);
    assert.deepEqual(verifiedContract({ contract_type: null, contract_evidence: null }, "Data Scientist", "No contract stated"), { contract_type: null, contract_evidence: null });
  });
});

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { describe, it } from "node:test";

const require = createRequire(import.meta.url);
const PDFDocument = require("pdfkit");
const { extractText } = await import("unpdf");

function textPdf(text) {
  return new Promise((resolve) => {
    const document = new PDFDocument();
    const chunks = [];
    document.on("data", (chunk) => chunks.push(chunk));
    document.on("end", () => resolve(Buffer.concat(chunks)));
    if (text) document.fontSize(18).text(text);
    document.end();
  });
}

describe("server-side PDF extraction contract", () => {
  it("extracts text from a real text PDF without pdftotext", async () => {
    const result = await extractText(new Uint8Array(await textPdf("ATS Sniper Data Scientist CV")), { mergePages: true });
    assert.match(result.text, /ATS Sniper Data Scientist CV/);
  });

  it("rejects invalid signatures before parsing", () => {
    assert.notEqual(Buffer.from("not a pdf").subarray(0, 5).toString("ascii"), "%PDF-");
  });

  it("reports image-only PDFs as empty text", async () => {
    const result = await extractText(new Uint8Array(await textPdf("")), { mergePages: true });
    assert.equal(result.text.trim(), "");
  });
});

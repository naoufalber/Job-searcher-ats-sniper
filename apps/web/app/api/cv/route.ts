import "server-only";
import { createHash, randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
const execFileAsync = promisify(execFile);
const MAX_BYTES = 5 * 1024 * 1024;

async function userClient() {
  const client = createClient();
  if (!client) return null;
  const { data } = await client.auth.getUser();
  return data.user ? { client, user: data.user } : null;
}

async function extractPdf(buffer: Buffer) {
  const dir = path.join(process.cwd(), ".tmp-cv");
  const file = path.join(dir, `${randomUUID()}.pdf`);
  await mkdir(dir, { recursive: true });
  try {
    await writeFile(file, buffer, { flag: "wx" });
    const { stdout } = await execFileAsync("pdftotext", ["-layout", file, "-"], { timeout: 15_000, maxBuffer: 2_000_000, windowsHide: true });
    return stdout.trim();
  } finally { await rm(file, { force: true }); }
}

export async function GET() {
  const session = await userClient();
  if (!session) return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  const { data, error } = await session.client.from("cv_documents").select("id,original_name,mime_type,size_bytes,content_hash,is_active,created_at").eq("user_id", session.user.id).order("created_at", { ascending: false });
  if (error) return NextResponse.json({ error: "Unable to load CVs." }, { status: 500 });
  return NextResponse.json({ documents: data ?? [] });
}

export async function POST(request: Request) {
  const session = await userClient();
  if (!session) return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  const form = await request.formData();
  const item = form.get("file");
  if (!(item instanceof File) || item.type !== "application/pdf" || item.size < 1 || item.size > MAX_BYTES) return NextResponse.json({ error: "Upload a PDF up to 5 MB." }, { status: 422 });
  const buffer = Buffer.from(await item.arrayBuffer());
  let extractedText = "";
  try { extractedText = await extractPdf(buffer); } catch { return NextResponse.json({ error: "PDF text extraction is unavailable. Install pdftotext and retry." }, { status: 422 }); }
  if (!extractedText) return NextResponse.json({ error: "The PDF contains no extractable text." }, { status: 422 });
  const hash = createHash("sha256").update(buffer).digest("hex");
  const storagePath = `${session.user.id}/${hash}.pdf`;
  const storage = session.client.storage.from("cv-documents");
  const uploaded = await storage.upload(storagePath, buffer, { contentType: "application/pdf", upsert: true });
  if (uploaded.error) return NextResponse.json({ error: "Unable to store CV." }, { status: 502 });
  await session.client.from("cv_documents").update({ is_active: false }).eq("user_id", session.user.id);
  const { data, error } = await session.client.from("cv_documents").upsert({ user_id: session.user.id, storage_path: storagePath, original_name: item.name || "cv.pdf", mime_type: "application/pdf", size_bytes: buffer.length, content_hash: hash, extracted_text: extractedText, is_active: true }, { onConflict: "storage_path" }).select("id,original_name,size_bytes,content_hash,is_active,created_at").single();
  if (error) { await storage.remove([storagePath]); return NextResponse.json({ error: "Unable to save CV metadata." }, { status: 500 }); }
  return NextResponse.json({ document: data }, { status: 201 });
}

export async function DELETE(request: Request) {
  const session = await userClient();
  if (!session) return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  const id = new URL(request.url).searchParams.get("id");
  if (!id) return NextResponse.json({ error: "Missing document id." }, { status: 400 });
  const { data } = await session.client.from("cv_documents").select("storage_path").eq("id", id).eq("user_id", session.user.id).maybeSingle();
  if (!data) return NextResponse.json({ error: "Not found." }, { status: 404 });
  await session.client.storage.from("cv-documents").remove([data.storage_path]);
  const { error } = await session.client.from("cv_documents").delete().eq("id", id).eq("user_id", session.user.id);
  if (error) return NextResponse.json({ error: "Unable to delete CV." }, { status: 500 });
  return NextResponse.json({ ok: true });
}

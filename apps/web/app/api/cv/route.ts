import "server-only";
import { createHash } from "node:crypto";
import { NextResponse } from "next/server";
import { extractText } from "unpdf";
import { createClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
const MAX_BYTES = 5 * 1024 * 1024;

async function userClient() {
  const client = createClient();
  if (!client) return null;
  const { data } = await client.auth.getUser();
  return data.user ? { client, user: data.user } : null;
}

async function extractPdf(buffer: Buffer) {
  if (buffer.subarray(0, 5).toString("ascii") !== "%PDF-") throw new Error("invalid_pdf_signature");
  const parsed = await extractText(new Uint8Array(buffer), { mergePages: true });
  return String(parsed.text ?? "").replace(/\u0000/g, "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
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
  try { extractedText = await extractPdf(buffer); } catch { return NextResponse.json({ error: "This PDF could not be parsed. It may be malformed or encrypted." }, { status: 422 }); }
  if (!extractedText) return NextResponse.json({ error: "No selectable text was found. This may be an image-only or scanned PDF; OCR is needed before matching." }, { status: 422 });
  const hash = createHash("sha256").update(buffer).digest("hex");
  const storagePath = `${session.user.id}/${hash}.pdf`;
  const storage = session.client.storage.from("cv-documents");
  const uploaded = await storage.upload(storagePath, buffer, { contentType: "application/pdf", upsert: true });
  if (uploaded.error) return NextResponse.json({ error: "Unable to store CV." }, { status: 502 });
  const { data: previous } = await session.client.from("cv_documents").select("id").eq("user_id", session.user.id).eq("is_active", true).maybeSingle();
  const { data, error } = await session.client.from("cv_documents").upsert({ user_id: session.user.id, storage_path: storagePath, original_name: item.name || "cv.pdf", mime_type: "application/pdf", size_bytes: buffer.length, content_hash: hash, extracted_text: extractedText, is_active: false }, { onConflict: "storage_path" }).select("id,original_name,size_bytes,content_hash,is_active,created_at").single();
  if (error || !data) { await storage.remove([storagePath]); return NextResponse.json({ error: "Unable to save CV metadata." }, { status: 500 }); }
  if (previous?.id && previous.id !== data.id) {
    const { error: deactivateError } = await session.client.from("cv_documents").update({ is_active: false }).eq("id", previous.id).eq("user_id", session.user.id);
    if (deactivateError) { await storage.remove([storagePath]); await session.client.from("cv_documents").delete().eq("id", data.id).eq("user_id", session.user.id); return NextResponse.json({ error: "Unable to replace the current CV; it was preserved." }, { status: 500 }); }
  }
  const { error: activateError } = await session.client.from("cv_documents").update({ is_active: true }).eq("id", data.id).eq("user_id", session.user.id);
  if (activateError) {
    if (previous?.id && previous.id !== data.id) await session.client.from("cv_documents").update({ is_active: true }).eq("id", previous.id).eq("user_id", session.user.id);
    await session.client.from("cv_documents").delete().eq("id", data.id).eq("user_id", session.user.id);
    await storage.remove([storagePath]);
    return NextResponse.json({ error: "Unable to activate the replacement CV; your previous CV was preserved." }, { status: 500 });
  }
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

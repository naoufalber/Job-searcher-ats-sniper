import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const next = requestUrl.searchParams.get("next");
  const safeNext = next?.startsWith("/") && !next.startsWith("//") ? next : "/onboarding";
  const supabase = createClient();
  if (!supabase || !code) return NextResponse.redirect(new URL("/login?error=auth_callback_invalid", requestUrl.origin));
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(new URL("/login?error=auth_link_invalid", requestUrl.origin));
  return NextResponse.redirect(new URL(safeNext, requestUrl.origin));
}

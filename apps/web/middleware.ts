import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return response;

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() { return request.cookies.getAll(); },
      setAll(cookies: { name: string; value: string; options: CookieOptions }[]) {
        cookies.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookies.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });
  const pathname = request.nextUrl.pathname;
  const apiPath = pathname.startsWith("/api/");
  const { data: { user } } = await supabase.auth.getUser();
  const publicPath = pathname === "/"
    || pathname === "/login"
    || pathname === "/auth/callback"
    || pathname === "/auth/update-password";

  if (!user && !publicPath && !apiPath) {
    const next = `${pathname}${request.nextUrl.search}`;
    return NextResponse.redirect(new URL(`/login?next=${encodeURIComponent(next)}`, request.url));
  }

  if (user && pathname === "/login") {
    const requestedNext = request.nextUrl.searchParams.get("next");
    const safeNext = requestedNext?.startsWith("/") && !requestedNext.startsWith("//") ? requestedNext : "/jobs";
    return NextResponse.redirect(new URL(safeNext, request.url));
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

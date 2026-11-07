import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";

export function createClient() {
  const cookieStore = cookies();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;

  return createServerClient(url, key, {
    cookies: {
      getAll() { return cookieStore.getAll(); },
      setAll(cookies: { name: string; value: string; options: CookieOptions }[]) {
        try {
          cookies.forEach(({ name, value, options }) => cookieStore.set({ name, value, ...options }));
        } catch {
          // Server components cannot always mutate cookies; middleware refreshes sessions.
        }
      },
    },
  });
}

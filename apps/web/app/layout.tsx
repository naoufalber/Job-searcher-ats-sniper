import type { Metadata } from "next";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { AccountControls } from "@/components/account-controls";
import "./globals.css";

export const metadata: Metadata = {
  title: "ATS Sniper | Job discovery",
  description: "A focused workspace for finding and tracking relevant roles.",
};

const nav = [
  ["Discover", "/jobs"],
  ["Saved", "/saved"],
  ["Tracker", "/tracker"],
  ["Settings", "/settings"],
];

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const supabase = createClient();
  const signedIn = Boolean((await supabase?.auth.getUser())?.data.user);
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-line bg-paper/95">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5 lg:px-10">
              <Link href="/" className="focus-ring flex items-center gap-3 rounded-md">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-moss text-sm font-semibold text-white">A</span>
                <span className="text-sm font-semibold tracking-[0.18em] text-ink">ATS SNIPER</span>
              </Link>
              <nav aria-label="Primary navigation" className="hidden items-center gap-7 text-sm text-slate-600 md:flex">
                {nav.map(([label, href]) => <Link className="focus-ring rounded py-2 transition hover:text-moss" href={href} key={href}>{label}</Link>)}
              </nav>
              <AccountControls signedIn={signedIn} />
            </div>
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}

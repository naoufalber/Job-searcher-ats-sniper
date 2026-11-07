import Link from "next/link";
import { signOut } from "@/app/auth/actions";

export function AccountControls({ signedIn }: { signedIn: boolean }) {
  if (!signedIn) return <Link href="/login" className="focus-ring rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-ink shadow-sm transition hover:border-moss hover:text-moss">Sign in</Link>;
  return <form action={signOut}><button className="focus-ring rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-ink shadow-sm transition hover:border-moss hover:text-moss" type="submit">Sign out</button></form>;
}

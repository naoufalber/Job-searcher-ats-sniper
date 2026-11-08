import { CvManager } from "@/components/cv-manager";

export default function CvPage() {
  return <main className="mx-auto max-w-4xl px-6 py-12 lg:px-10"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Private workspace</p><h1 className="mt-2 text-4xl font-semibold tracking-tight text-ink">Your CV</h1><p className="mt-3 text-slate-500">Upload one private PDF. Its extracted text is used only for your authenticated job analysis.</p><div className="mt-8"><CvManager /></div></main>;
}

"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";

type PageItem = number | "ellipsis-left" | "ellipsis-right";

function pageItems(currentPage: number, totalPages: number): PageItem[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1);
  if (currentPage <= 4) return [1, 2, 3, 4, 5, "ellipsis-right", totalPages];
  if (currentPage >= totalPages - 3) return [1, "ellipsis-left", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  return [1, "ellipsis-left", currentPage - 1, currentPage, currentPage + 1, "ellipsis-right", totalPages];
}

export function JobsPagination({ currentPage, totalPages, previousHref, nextHref, hrefForPage }: { currentPage: number; totalPages: number; previousHref: string; nextHref: string; hrefForPage: (page: number) => string }) {
  const activeRef = useRef<HTMLAnchorElement>(null);
  const items = useMemo(() => pageItems(currentPage, totalPages), [currentPage, totalPages]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [currentPage]);

  if (totalPages <= 1) return null;

  return <nav className="mt-8 flex items-center justify-between gap-3" aria-label="Job pages">
    {currentPage > 1 ? <Link className="focus-ring inline-flex shrink-0 items-center rounded-full px-2 py-2 text-sm font-semibold text-slate-500 transition-colors hover:bg-paper hover:text-ink sm:px-3" href={previousHref} rel="prev">Previous</Link> : <span aria-disabled="true" className="inline-flex shrink-0 items-center rounded-full px-2 py-2 text-sm font-semibold text-slate-300 sm:px-3">Previous</span>}
    <div className="min-w-0 max-w-[min(64vw,27rem)] overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" tabIndex={0} aria-label={`Page ${currentPage} of ${totalPages}`}>
      <div className="flex min-w-max items-center gap-1 px-1 py-1">
        {items.map((item) => item === "ellipsis-left" || item === "ellipsis-right" ? <span key={item} className="px-2 text-sm text-slate-300" aria-hidden="true">...</span> : <Link key={item} ref={item === currentPage ? activeRef : undefined} className={item === currentPage ? "focus-ring inline-flex h-9 min-w-9 items-center justify-center rounded-full bg-moss px-3 text-sm font-semibold text-white shadow-sm transition-transform duration-200" : "focus-ring inline-flex h-9 min-w-9 items-center justify-center rounded-full px-3 text-sm font-medium text-slate-400 transition-colors duration-200 hover:bg-paper hover:text-ink"} href={hrefForPage(item)} aria-current={item === currentPage ? "page" : undefined}>{item}</Link>)}
      </div>
    </div>
    {currentPage < totalPages ? <Link className="focus-ring inline-flex shrink-0 items-center rounded-full px-2 py-2 text-sm font-semibold text-slate-500 transition-colors hover:bg-paper hover:text-ink sm:px-3" href={nextHref} rel="next">Next</Link> : <span aria-disabled="true" className="inline-flex shrink-0 items-center rounded-full px-2 py-2 text-sm font-semibold text-slate-300 sm:px-3">Next</span>}
  </nav>;
}

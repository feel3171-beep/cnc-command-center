"use client";

import { usePathname } from "next/navigation";
import { Search, Bell } from "lucide-react";

const PAGE_TITLES: Record<string, string> = {
  "/": "대시보드",
  "/board": "태스크 보드",
  "/agents": "에이전트",
  "/scheduler": "스케줄러",
  "/dashboards/production": "생산 현황",
  "/dashboards/sales": "매출 현황",
  "/dashboards/delivery": "납기 현황",
  "/agents/hr": "인사 에이전트",
};

export function Header() {
  const pathname = usePathname();
  const title =
    PAGE_TITLES[pathname] ||
    Object.entries(PAGE_TITLES).find(([k]) => pathname.startsWith(k))?.[1] ||
    "Command Center";

  return (
    <header className="h-14 bg-bg-secondary border-b border-border-primary flex items-center justify-between px-6 shrink-0">
      <h1 className="text-lg font-semibold text-text-primary">{title}</h1>

      <div className="flex items-center gap-3">
        <button className="flex items-center gap-2 px-3 py-1.5 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-muted hover:text-text-secondary transition-colors">
          <Search size={14} />
          <span>검색...</span>
          <kbd className="ml-4 px-1.5 py-0.5 bg-bg-primary rounded text-xs">
            ⌘K
          </kbd>
        </button>
        <button className="relative p-2 text-text-secondary hover:text-text-primary transition-colors">
          <Bell size={18} />
          <span className="absolute top-1 right-1 w-2 h-2 bg-accent-red rounded-full" />
        </button>
      </div>
    </header>
  );
}

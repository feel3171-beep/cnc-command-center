"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Kanban,
  Bot,
  Calendar,
  BarChart3,
  Factory,
  DollarSign,
  Users,
  Calculator,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "대시보드", icon: LayoutDashboard },
  { href: "/board", label: "태스크 보드", icon: Kanban },
  { type: "divider" as const },
  { href: "/agents", label: "에이전트", icon: Bot },
  { href: "/scheduler", label: "스케줄러", icon: Calendar },
  { type: "divider" as const },
  { href: "/dashboards/production", label: "생산 현황", icon: Factory },
  { href: "/dashboards/sales", label: "매출 현황", icon: DollarSign },
  { href: "/dashboards/delivery", label: "납기 현황", icon: BarChart3 },
  { type: "divider" as const },
  { href: "/agents/production", label: "생산 Agent", icon: Factory },
  { href: "/agents/hr", label: "인사 Agent", icon: Users },
  { href: "/agents/finance", label: "재무 Agent", icon: DollarSign },
  { href: "/agents/cost", label: "원가 Agent", icon: Calculator },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 bg-bg-secondary border-r border-border-primary flex flex-col shrink-0">
      <div className="h-14 flex items-center px-4 border-b border-border-primary">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-accent-green flex items-center justify-center text-black font-bold text-sm">
            C
          </div>
          <span className="font-semibold text-sm text-text-primary">
            Command Center
          </span>
        </div>
      </div>

      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV_ITEMS.map((item, i) => {
          if ("type" in item && item.type === "divider") {
            return (
              <div
                key={`d-${i}`}
                className="my-2 mx-3 border-t border-border-primary"
              />
            );
          }
          if (!("href" in item)) return null;
          const Icon = item.icon;
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-2.5 px-3 py-2 mx-2 rounded-md text-sm transition-colors",
                isActive
                  ? "bg-bg-active text-text-primary"
                  : "text-text-secondary hover:bg-bg-hover hover:text-text-primary"
              )}
            >
              <Icon size={16} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-3 border-t border-border-primary">
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <div className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
          에이전트 활성
        </div>
      </div>
    </aside>
  );
}

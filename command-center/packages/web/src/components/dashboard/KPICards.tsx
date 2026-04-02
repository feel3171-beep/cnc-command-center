"use client";

import { useEffect, useState } from "react";
import { Factory, TrendingUp, AlertTriangle, Package } from "lucide-react";
import type { KPIData } from "@/types/task";

export function KPICards() {
  const [kpi, setKpi] = useState<KPIData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/kpi")
      .then((r) => r.json())
      .then(setKpi)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="h-28 bg-bg-secondary rounded-lg border border-border-primary animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (!kpi) {
    return (
      <div className="grid grid-cols-4 gap-4">
        <Card
          icon={Factory}
          label="생산 달성률"
          value="--"
          sub="MES 연결 대기"
          color="text-text-muted"
        />
        <Card
          icon={TrendingUp}
          label="금일 실적"
          value="--"
          sub=""
          color="text-text-muted"
        />
        <Card
          icon={Package}
          label="양품률"
          value="--"
          sub=""
          color="text-text-muted"
        />
        <Card
          icon={AlertTriangle}
          label="불량"
          value="--"
          sub=""
          color="text-text-muted"
        />
      </div>
    );
  }

  const t = kpi.total;
  return (
    <div className="grid grid-cols-4 gap-4">
      <Card
        icon={Factory}
        label="생산 달성률"
        value={`${t.achievement_rate}%`}
        sub={`계획 ${t.plan_qty.toLocaleString()} → 실적 ${t.actual_qty.toLocaleString()}`}
        color={
          t.achievement_rate >= 80
            ? "text-accent-green"
            : t.achievement_rate >= 50
            ? "text-accent-yellow"
            : "text-accent-red"
        }
      />
      <Card
        icon={TrendingUp}
        label="금일 실적"
        value={t.actual_qty.toLocaleString()}
        sub={`${t.order_cnt}건 작업지시`}
        color="text-accent-blue"
      />
      <Card
        icon={Package}
        label="양품률"
        value={`${t.good_rate}%`}
        sub={`양품 ${t.good_qty.toLocaleString()}`}
        color={t.good_rate >= 99 ? "text-accent-green" : "text-accent-yellow"}
      />
      <Card
        icon={AlertTriangle}
        label="불량"
        value={t.loss_qty.toLocaleString()}
        sub={`불량률 ${(100 - t.good_rate).toFixed(1)}%`}
        color={t.loss_qty > 0 ? "text-accent-red" : "text-accent-green"}
      />
    </div>
  );
}

function Card({
  icon: Icon,
  label,
  value,
  sub,
  color,
}: {
  icon: React.ComponentType<any>;
  label: string;
  value: string;
  sub: string;
  color: string;
}) {
  return (
    <div className="bg-bg-secondary rounded-lg border border-border-primary p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="text-text-muted" />
        <span className="text-xs text-text-muted">{label}</span>
      </div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-text-muted mt-1">{sub}</div>
    </div>
  );
}

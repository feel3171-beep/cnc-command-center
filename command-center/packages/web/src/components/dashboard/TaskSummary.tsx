import { STATUS_LABELS, type TaskStatus } from "@/types/task";

const STATUS_ORDER: TaskStatus[] = ["INBOX", "WIP", "REVIEW", "FINAL"];
const STATUS_COLORS: Record<TaskStatus, string> = {
  INBOX: "bg-text-muted",
  WIP: "bg-accent-blue",
  REVIEW: "bg-accent-orange",
  FINAL: "bg-accent-green",
  ARCHIVE: "bg-text-muted",
};

export function TaskSummary({ counts }: { counts: Record<string, number> }) {
  const total = STATUS_ORDER.reduce((s, k) => s + (counts[k] || 0), 0);

  return (
    <div className="space-y-3">
      <div className="text-3xl font-bold text-text-primary">{total}</div>
      <div className="flex gap-1 h-2 rounded-full overflow-hidden bg-bg-primary">
        {STATUS_ORDER.map((s) => {
          const c = counts[s] || 0;
          if (c === 0) return null;
          return (
            <div
              key={s}
              className={`${STATUS_COLORS[s]} transition-all`}
              style={{ width: `${(c / total) * 100}%` }}
            />
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {STATUS_ORDER.map((s) => (
          <div key={s} className="flex items-center gap-2 text-xs">
            <div className={`w-2 h-2 rounded-full ${STATUS_COLORS[s]}`} />
            <span className="text-text-secondary">{STATUS_LABELS[s]}</span>
            <span className="text-text-primary font-medium ml-auto">
              {counts[s] || 0}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

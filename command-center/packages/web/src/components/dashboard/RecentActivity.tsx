import type { Task } from "@/types/task";
import { PRIORITY_COLORS } from "@/types/task";

export function RecentActivity({ tasks }: { tasks: Task[] }) {
  if (tasks.length === 0) {
    return (
      <div className="text-sm text-text-muted py-4 text-center">
        아직 태스크가 없습니다
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {tasks.map((task) => (
        <div
          key={task.id}
          className="flex items-center gap-2 p-2 rounded-md hover:bg-bg-tertiary transition-colors"
        >
          <div
            className={`w-1.5 h-1.5 rounded-full ${PRIORITY_COLORS[task.priority]}`}
          />
          <div className="flex-1 min-w-0">
            <div className="text-sm text-text-primary truncate">
              {task.title}
            </div>
            <div className="text-xs text-text-muted">
              {task.project?.name || "프로젝트 없음"} &middot; {task.status}
            </div>
          </div>
          <span className="text-xs text-text-muted shrink-0">
            {new Date(task.updatedAt).toLocaleDateString("ko-KR", {
              month: "short",
              day: "numeric",
            })}
          </span>
        </div>
      ))}
    </div>
  );
}

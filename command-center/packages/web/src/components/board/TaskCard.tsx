"use client";

import Link from "next/link";
import { MessageCircle, FileText, Calendar } from "lucide-react";
import {
  PRIORITY_COLORS,
  AGENT_LABELS,
  AGENT_COLORS,
  type Task,
} from "@/types/task";

export function TaskCard({ task }: { task: Task }) {
  return (
    <Link
      href={`/board/${task.id}`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("taskId", task.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      className="block p-3 bg-bg-secondary border border-border-primary rounded-lg hover:border-border-secondary transition-colors cursor-grab active:cursor-grabbing"
    >
      <div className="flex items-start gap-2 mb-2">
        <div
          className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${PRIORITY_COLORS[task.priority]}`}
        />
        <span className="text-sm text-text-primary leading-snug line-clamp-2">
          {task.title}
        </span>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {task.project && (
          <span
            className="text-xs px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: task.project.color + "20",
              color: task.project.color,
            }}
          >
            {task.project.name}
          </span>
        )}
        {task.agentType && (
          <span className={`text-xs ${AGENT_COLORS[task.agentType]}`}>
            {AGENT_LABELS[task.agentType]}
          </span>
        )}
        {task.priority === "P0" && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-priority-p0/20 text-priority-p0 font-medium">
            P0
          </span>
        )}
        {task.priority === "P1" && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-priority-p1/20 text-priority-p1">
            P1
          </span>
        )}
      </div>

      <div className="flex items-center gap-3 mt-2 text-text-muted">
        {task._count && task._count.chatMessages > 0 && (
          <span className="flex items-center gap-1 text-xs">
            <MessageCircle size={11} />
            {task._count.chatMessages}
          </span>
        )}
        {task._count && task._count.outputs > 0 && (
          <span className="flex items-center gap-1 text-xs">
            <FileText size={11} />
            {task._count.outputs}
          </span>
        )}
        {task.dueDate && (
          <span className="flex items-center gap-1 text-xs ml-auto">
            <Calendar size={11} />
            {new Date(task.dueDate).toLocaleDateString("ko-KR", {
              month: "short",
              day: "numeric",
            })}
          </span>
        )}
      </div>
    </Link>
  );
}

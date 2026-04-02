"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import {
  STATUS_LABELS,
  PRIORITY_COLORS,
  AGENT_LABELS,
  AGENT_COLORS,
  type Task,
  type TaskStatus,
  type Project,
  type Priority,
  type AgentType,
} from "@/types/task";
import { TaskCard } from "./TaskCard";
import { CreateTaskModal } from "./CreateTaskModal";

const STATUS_HEADER_COLORS: Record<TaskStatus, string> = {
  INBOX: "border-text-muted",
  WIP: "border-accent-blue",
  REVIEW: "border-accent-orange",
  FINAL: "border-accent-green",
  ARCHIVE: "border-text-muted",
};

interface Props {
  columns: Record<string, Task[]>;
  projects: Project[];
}

export function KanbanBoard({ columns, projects }: Props) {
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);
  const [dragOverCol, setDragOverCol] = useState<string | null>(null);

  const handleDrop = useCallback(
    async (taskId: string, newStatus: TaskStatus) => {
      await fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      router.refresh();
    },
    [router]
  );

  const statuses: TaskStatus[] = ["INBOX", "WIP", "REVIEW", "FINAL"];

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          {statuses.map((s) => (
            <span key={s} className="text-xs text-text-muted">
              {STATUS_LABELS[s]}{" "}
              <span className="text-text-primary font-medium">
                {(columns[s] || []).length}
              </span>
            </span>
          ))}
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-accent-green text-black rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
        >
          <Plus size={14} />
          태스크 생성
        </button>
      </div>

      <div className="flex gap-4 h-full">
        {statuses.map((status) => (
          <div
            key={status}
            className={`flex-1 min-w-[280px] kanban-column rounded-lg transition-colors ${
              dragOverCol === status ? "bg-bg-hover" : ""
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOverCol(status);
            }}
            onDragLeave={() => setDragOverCol(null)}
            onDrop={(e) => {
              e.preventDefault();
              const taskId = e.dataTransfer.getData("taskId");
              if (taskId) handleDrop(taskId, status);
              setDragOverCol(null);
            }}
          >
            <div
              className={`flex items-center gap-2 mb-3 pb-2 border-b-2 ${STATUS_HEADER_COLORS[status]}`}
            >
              <span className="text-sm font-medium text-text-primary">
                {STATUS_LABELS[status]}
              </span>
              <span className="text-xs text-text-muted bg-bg-tertiary px-1.5 py-0.5 rounded">
                {(columns[status] || []).length}
              </span>
            </div>

            <div className="space-y-2">
              {(columns[status] || []).map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {showCreate && (
        <CreateTaskModal
          projects={projects}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            router.refresh();
          }}
        />
      )}
    </>
  );
}

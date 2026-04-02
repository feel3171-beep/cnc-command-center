"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Trash2,
  FileText,
  Bot,
  User,
  MessageCircle,
} from "lucide-react";
import Link from "next/link";
import {
  STATUS_LABELS,
  PRIORITY_COLORS,
  AGENT_LABELS,
  PM_ROLE_LABELS,
  type Task,
  type TaskOutput,
  type TaskStatus,
  type Priority,
  type AgentType,
  type PMRole,
} from "@/types/task";

interface FullTask extends Task {
  outputs: TaskOutput[];
}

type ActiveTab = "staff" | "pm";

export function TaskDetail({ task }: { task: FullTask }) {
  const router = useRouter();
  const [status, setStatus] = useState<TaskStatus>(task.status);
  const [priority, setPriority] = useState<Priority>(task.priority);
  const [activeTab, setActiveTab] = useState<ActiveTab>("staff");

  const updateField = async (field: string, value: unknown) => {
    await fetch(`/api/tasks/${task.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [field]: value }),
    });
    router.refresh();
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          href="/board"
          className="p-1.5 text-text-muted hover:text-text-primary transition-colors"
        >
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-xl font-semibold text-text-primary flex-1">
          {task.title}
        </h1>
        <button
          onClick={async () => {
            await fetch(`/api/tasks/${task.id}`, { method: "DELETE" });
            router.push("/board");
          }}
          className="p-2 text-text-muted hover:text-accent-red transition-colors"
        >
          <Trash2 size={16} />
        </button>
      </div>

      {/* Status bar */}
      <div className="flex gap-3 flex-wrap">
        <select
          value={status}
          onChange={(e) => {
            const v = e.target.value as TaskStatus;
            setStatus(v);
            updateField("status", v);
          }}
          className="px-3 py-1.5 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-primary"
        >
          {(["INBOX", "WIP", "REVIEW", "FINAL"] as TaskStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>

        <select
          value={priority}
          onChange={(e) => {
            const v = e.target.value as Priority;
            setPriority(v);
            updateField("priority", v);
          }}
          className="px-3 py-1.5 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-primary"
        >
          {(["P0", "P1", "P2", "P3"] as Priority[]).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>

        {task.project && (
          <span
            className="px-3 py-1.5 rounded-md text-sm"
            style={{
              backgroundColor: task.project.color + "20",
              color: task.project.color,
            }}
          >
            {task.project.name}
          </span>
        )}
        {task.agentType && (
          <span className="px-3 py-1.5 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-secondary">
            {AGENT_LABELS[task.agentType]} Agent
          </span>
        )}
        {task.pmRole && (
          <span className="px-3 py-1.5 bg-accent-purple/10 border border-accent-purple/30 rounded-md text-sm text-accent-purple">
            PM: {PM_ROLE_LABELS[task.pmRole]}
            {task.pmName ? ` (${task.pmName})` : ""}
          </span>
        )}
      </div>

      {/* Staff / PM Tab */}
      <div className="flex border-b border-border-primary">
        <button
          onClick={() => setActiveTab("staff")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "staff"
              ? "border-accent-green text-text-primary"
              : "border-transparent text-text-muted hover:text-text-secondary"
          }`}
        >
          <Bot size={15} />
          Staff
        </button>
        <button
          onClick={() => setActiveTab("pm")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "pm"
              ? "border-accent-purple text-text-primary"
              : "border-transparent text-text-muted hover:text-text-secondary"
          }`}
        >
          <User size={15} />
          PM
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === "staff" ? (
        <StaffTab task={task} />
      ) : (
        <PMTab task={task} onUpdate={updateField} />
      )}
    </div>
  );
}

function StaffTab({ task }: { task: FullTask }) {
  return (
    <div className="space-y-4">
      {/* Description */}
      {task.description && (
        <div className="p-4 bg-bg-tertiary rounded-lg text-sm text-text-secondary whitespace-pre-wrap">
          {task.description}
        </div>
      )}

      {/* Agent execution area */}
      <div className="p-4 bg-bg-tertiary rounded-lg border border-border-primary">
        <div className="flex items-center gap-2 mb-3">
          <Bot size={16} className="text-accent-green" />
          <span className="text-sm font-medium text-text-primary">
            에이전트 실행
          </span>
          {task.agentType && (
            <span className="text-xs text-text-muted ml-auto">
              {AGENT_LABELS[task.agentType]}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 bg-accent-green text-black rounded-md text-sm font-medium hover:opacity-90 transition-opacity">
            Output 생성
          </button>
          <button className="px-3 py-1.5 bg-bg-secondary border border-border-primary rounded-md text-sm text-text-secondary hover:text-text-primary transition-colors">
            <MessageCircle size={13} className="inline mr-1" />
            Chat
          </button>
        </div>
      </div>

      {/* Outputs */}
      {task.outputs && task.outputs.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-text-secondary mb-2">
            Output ({task.outputs.length})
          </h3>
          <div className="space-y-2">
            {task.outputs.map((o) => (
              <details
                key={o.id}
                className="bg-bg-tertiary border border-border-primary rounded-lg"
              >
                <summary className="px-4 py-2 cursor-pointer flex items-center gap-2 text-sm text-text-primary">
                  <FileText size={14} className="text-text-muted" />
                  {o.filename}
                  <span className="text-xs text-text-muted ml-auto">
                    {o.createdBy} &middot;{" "}
                    {new Date(o.createdAt).toLocaleString("ko-KR")}
                  </span>
                </summary>
                <div className="px-4 py-3 border-t border-border-primary text-sm text-text-secondary whitespace-pre-wrap max-h-96 overflow-y-auto">
                  {o.content}
                </div>
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PMTab({
  task,
  onUpdate,
}: {
  task: FullTask;
  onUpdate: (field: string, value: unknown) => void;
}) {
  const [pmRole, setPmRole] = useState(task.pmRole || "");
  const [pmName, setPmName] = useState(task.pmName || "");

  return (
    <div className="space-y-4">
      {/* PM Assignment */}
      <div className="p-4 bg-bg-tertiary rounded-lg border border-accent-purple/20">
        <h3 className="text-sm font-medium text-accent-purple mb-3">
          PM 배정
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-text-muted mb-1">
              PM 역할
            </label>
            <select
              value={pmRole}
              onChange={(e) => {
                setPmRole(e.target.value);
                onUpdate("pmRole", e.target.value || null);
              }}
              className="w-full px-2 py-1.5 bg-bg-secondary border border-border-primary rounded-md text-sm text-text-primary"
            >
              <option value="">미배정</option>
              <option value="FPA">FP&A</option>
              <option value="HR_LEAD">인사팀장</option>
              <option value="PROD_LEAD">생산팀장</option>
              <option value="COST_LEAD">원가팀장</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">
              PM 이름
            </label>
            <input
              value={pmName}
              onChange={(e) => setPmName(e.target.value)}
              onBlur={() => onUpdate("pmName", pmName || null)}
              placeholder="이름 입력"
              className="w-full px-2 py-1.5 bg-bg-secondary border border-border-primary rounded-md text-sm text-text-primary placeholder:text-text-muted"
            />
          </div>
        </div>
      </div>

      {/* PM Review Status */}
      <div className="p-4 bg-bg-tertiary rounded-lg border border-border-primary">
        <h3 className="text-sm font-medium text-text-secondary mb-3">
          리뷰 상태
        </h3>
        <div className="flex gap-2">
          <button
            onClick={() => onUpdate("status", "WIP")}
            className="px-3 py-1.5 bg-bg-secondary border border-border-primary rounded-md text-sm text-text-secondary hover:border-accent-blue transition-colors"
          >
            WIP
          </button>
          <button
            onClick={() => onUpdate("status", "REVIEW")}
            className="px-3 py-1.5 bg-accent-orange/10 border border-accent-orange/30 rounded-md text-sm text-accent-orange"
          >
            Awaiting Review
          </button>
          <button
            onClick={() => onUpdate("status", "FINAL")}
            className="px-3 py-1.5 bg-accent-green/10 border border-accent-green/30 rounded-md text-sm text-accent-green"
          >
            완료
          </button>
        </div>
      </div>

      {/* PM Direction / Context */}
      <div className="p-4 bg-bg-tertiary rounded-lg border border-border-primary">
        <h3 className="text-sm font-medium text-text-secondary mb-2">
          PM 방향 설정
        </h3>
        <p className="text-xs text-text-muted mb-3">
          PM Chat에서 에이전트에게 분석 방향을 지시할 수 있습니다.
          Staff Chat과 분리된 별도 대화입니다.
        </p>
        <div className="text-xs text-text-muted space-y-1">
          <div>
            &bull; Staff: 실무 분석 실행, Output 생성, 데이터 작업
          </div>
          <div>
            &bull; PM: 태스크 할당, 리뷰/승인, 방향 설정, 최종 판단
          </div>
        </div>
      </div>
    </div>
  );
}

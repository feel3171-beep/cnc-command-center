"use client";

import { useState } from "react";
import { X } from "lucide-react";
import type { Project, Priority, AgentType, PMRole, TaskStatus } from "@/types/task";

interface Props {
  projects: Project[];
  onClose: () => void;
  onCreated: () => void;
}

export function CreateTaskModal({ projects, onClose, onCreated }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("P2");
  const [status, setStatus] = useState<TaskStatus>("INBOX");
  const [projectId, setProjectId] = useState("");
  const [agentType, setAgentType] = useState<AgentType | "">("");
  const [pmRole, setPmRole] = useState<PMRole | "">("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);

    await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title.trim(),
        description: description.trim() || null,
        priority,
        status,
        projectId: projectId || null,
        agentType: agentType || null,
        pmRole: pmRole || null,
      }),
    });

    onCreated();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-lg bg-bg-secondary border border-border-primary rounded-xl p-6 space-y-4"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text-primary">
            태스크 생성
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-text-muted hover:text-text-primary"
          >
            <X size={18} />
          </button>
        </div>

        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="태스크 제목"
          className="w-full px-3 py-2 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-blue"
        />

        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="설명 (선택)"
          rows={3}
          className="w-full px-3 py-2 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-blue resize-none"
        />

        <div className="grid grid-cols-2 gap-3">
          <Select
            label="우선순위"
            value={priority}
            onChange={(v) => setPriority(v as Priority)}
            options={[
              { value: "P0", label: "P0 — 긴급" },
              { value: "P1", label: "P1 — 높음" },
              { value: "P2", label: "P2 — 보통" },
              { value: "P3", label: "P3 — 낮음" },
            ]}
          />
          <Select
            label="상태"
            value={status}
            onChange={(v) => setStatus(v as TaskStatus)}
            options={[
              { value: "INBOX", label: "Inbox" },
              { value: "WIP", label: "WIP" },
              { value: "REVIEW", label: "Review" },
              { value: "FINAL", label: "Final" },
            ]}
          />
          <Select
            label="프로젝트"
            value={projectId}
            onChange={setProjectId}
            options={[
              { value: "", label: "없음" },
              ...projects.map((p) => ({ value: p.id, label: p.name })),
            ]}
          />
          <Select
            label="에이전트"
            value={agentType}
            onChange={(v) => setAgentType(v as AgentType | "")}
            options={[
              { value: "", label: "없음" },
              { value: "PRODUCTION", label: "생산" },
              { value: "HR", label: "인사" },
              { value: "FINANCE", label: "재무" },
              { value: "COST", label: "원가" },
            ]}
          />
          <Select
            label="PM"
            value={pmRole}
            onChange={(v) => setPmRole(v as PMRole | "")}
            options={[
              { value: "", label: "미배정" },
              { value: "FPA", label: "FP&A" },
              { value: "HR_LEAD", label: "인사팀장" },
              { value: "PROD_LEAD", label: "생산팀장" },
              { value: "COST_LEAD", label: "원가팀장" },
            ]}
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={!title.trim() || saving}
            className="px-4 py-2 bg-accent-green text-black rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {saving ? "생성 중..." : "생성"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <label className="block text-xs text-text-muted mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1.5 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-primary focus:outline-none focus:border-accent-blue"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

"use client";

import { useState } from "react";
import { Bot, User } from "lucide-react";
import { PMChatPanel } from "./PMChatPanel";
import {
  AGENT_LABELS,
  PM_ROLE_LABELS,
  type AgentType,
  type PMRole,
  type ChatMessage,
} from "@/types/task";

interface Props {
  taskId: string;
  agentType?: AgentType | null;
  pmRole?: PMRole | null;
  pmName?: string | null;
  staffMessages: ChatMessage[];
  pmMessages: ChatMessage[];
}

type ChatTab = "staff" | "pm";

export function DualChatPanel({
  taskId,
  agentType,
  pmRole,
  pmName,
  staffMessages,
  pmMessages,
}: Props) {
  const [activeChat, setActiveChat] = useState<ChatTab>("staff");

  return (
    <div className="h-full flex flex-col">
      {/* Tab bar */}
      <div className="flex bg-bg-secondary border border-border-primary rounded-t-lg overflow-hidden">
        <button
          onClick={() => setActiveChat("staff")}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors ${
            activeChat === "staff"
              ? "bg-bg-tertiary text-accent-green border-b-2 border-accent-green"
              : "text-text-muted hover:text-text-secondary"
          }`}
        >
          <Bot size={14} />
          Staff
          {agentType && (
            <span className="text-xs opacity-60">
              {AGENT_LABELS[agentType]}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveChat("pm")}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors ${
            activeChat === "pm"
              ? "bg-bg-tertiary text-accent-purple border-b-2 border-accent-purple"
              : "text-text-muted hover:text-text-secondary"
          }`}
        >
          <User size={14} />
          PM
          {pmRole && (
            <span className="text-xs opacity-60">
              {PM_ROLE_LABELS[pmRole]}
            </span>
          )}
        </button>
      </div>

      {/* Chat panel */}
      <div className="flex-1 min-h-0">
        {activeChat === "staff" ? (
          <PMChatPanel
            taskId={taskId}
            initialMessages={staffMessages}
            agentType={agentType}
            channel="staff"
            accentColor="accent-green"
            placeholder="Staff에게 분석을 요청하세요..."
            emptyMessage={
              "Staff Chat — 에이전트에게 데이터 분석, Output 생성을 지시합니다.\nMES 데이터, Google Sheets, Slack 히스토리를 참조할 수 있습니다."
            }
          />
        ) : (
          <PMChatPanel
            taskId={taskId}
            initialMessages={pmMessages}
            agentType={agentType}
            channel="pm"
            accentColor="accent-purple"
            placeholder={`${pmRole ? PM_ROLE_LABELS[pmRole] : "PM"}에게 방향을 설정하세요...`}
            emptyMessage={
              `PM Chat — ${pmName || "PM"}과의 대화입니다.\n리뷰 피드백, 방향 설정, 최종 판단을 요청합니다.`
            }
          />
        )}
      </div>
    </div>
  );
}

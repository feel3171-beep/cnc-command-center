import { AGENT_LABELS, AGENT_COLORS, type AgentType } from "@/types/task";
import { Bot, CheckCircle, XCircle, Loader } from "lucide-react";

interface Run {
  id: string;
  agentType: AgentType;
  status: string;
  startedAt: string;
  completedAt?: string | null;
  turnsUsed: number;
}

const AGENTS: AgentType[] = ["PRODUCTION", "HR", "FINANCE"];

export function AgentStatus({ runs }: { runs: Run[] }) {
  return (
    <div className="space-y-3">
      {AGENTS.map((type) => {
        const lastRun = runs.find((r) => r.agentType === type);
        return (
          <div
            key={type}
            className="flex items-center gap-3 p-2 rounded-md bg-bg-tertiary"
          >
            <Bot size={16} className={AGENT_COLORS[type]} />
            <div className="flex-1">
              <div className="text-sm font-medium text-text-primary">
                {AGENT_LABELS[type]} Agent
              </div>
              <div className="text-xs text-text-muted">
                {lastRun
                  ? `마지막 실행: ${new Date(lastRun.startedAt).toLocaleString("ko-KR")}`
                  : "실행 기록 없음"}
              </div>
            </div>
            {lastRun ? (
              lastRun.status === "SUCCESS" ? (
                <CheckCircle size={14} className="text-accent-green" />
              ) : lastRun.status === "RUNNING" ? (
                <Loader size={14} className="text-accent-blue animate-spin" />
              ) : (
                <XCircle size={14} className="text-accent-red" />
              )
            ) : (
              <div className="w-2 h-2 rounded-full bg-text-muted" />
            )}
          </div>
        );
      })}
    </div>
  );
}

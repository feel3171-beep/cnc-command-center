"use client";

import { useState } from "react";
import { Bot, Play, Loader, CheckCircle, XCircle } from "lucide-react";

const AGENTS = [
  {
    type: "PRODUCTION",
    label: "생산 Agent",
    desc: "MES 데이터 분석, 생산 현황, 품질 이상 감지, 납기 추적",
    pm: "생산팀장",
    color: "text-accent-green",
    bgColor: "bg-accent-green/10",
  },
  {
    type: "HR",
    label: "인사 Agent",
    desc: "채용 파이프라인, 인재 매칭, 인력 분석",
    pm: "인사팀장",
    color: "text-accent-purple",
    bgColor: "bg-accent-purple/10",
  },
  {
    type: "FINANCE",
    label: "재무 Agent",
    desc: "매출/수주 분석, 납기 리스크, 경영진 브리핑",
    pm: "FP&A",
    color: "text-accent-blue",
    bgColor: "bg-accent-blue/10",
  },
  {
    type: "COST",
    label: "원가 Agent",
    desc: "BOM 기반 원가 분석, 불량 비용 산출, 수익성 분석",
    pm: "원가팀장",
    color: "text-accent-orange",
    bgColor: "bg-accent-orange/10",
    badge: "데이터 준비 중",
  },
];

export default function AgentsPage() {
  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, any>>({});

  const runAgent = async (agentType: string, mission: string) => {
    setRunning(agentType);
    try {
      const res = await fetch(`/api/agents/${agentType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mission }),
      });
      const data = await res.json();
      setResults((prev) => ({ ...prev, [agentType]: data }));
    } catch (e: any) {
      setResults((prev) => ({
        ...prev,
        [agentType]: { status: "FAILED", error: e.message },
      }));
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        {AGENTS.map((agent) => (
          <div
            key={agent.type}
            className="bg-bg-secondary border border-border-primary rounded-lg p-5"
          >
            <div className="flex items-center gap-3 mb-3">
              <div
                className={`w-10 h-10 rounded-lg ${agent.bgColor} flex items-center justify-center`}
              >
                <Bot size={20} className={agent.color} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-text-primary">
                    {agent.label}
                  </h3>
                  {"badge" in agent && agent.badge && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-accent-orange/20 text-accent-orange rounded">
                      {agent.badge}
                    </span>
                  )}
                </div>
                <p className="text-xs text-text-muted">{agent.desc}</p>
                <p className="text-xs text-text-muted mt-0.5">
                  PM: <span className="text-accent-purple">{agent.pm}</span>
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <button
                onClick={() =>
                  runAgent(
                    agent.type,
                    "오늘의 현황을 분석하고 핵심 인사이트를 도출하세요. Slack에 결과를 발송하세요."
                  )
                }
                disabled={running === agent.type}
                className="w-full flex items-center justify-center gap-2 py-2 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50 transition-colors"
              >
                {running === agent.type ? (
                  <>
                    <Loader size={14} className="animate-spin" />
                    실행 중...
                  </>
                ) : (
                  <>
                    <Play size={14} />
                    분석 실행
                  </>
                )}
              </button>
            </div>

            {results[agent.type] && (
              <div className="mt-3 p-3 bg-bg-tertiary rounded-md text-xs">
                <div className="flex items-center gap-1.5 mb-1">
                  {results[agent.type].status === "SUCCESS" ? (
                    <CheckCircle size={12} className="text-accent-green" />
                  ) : (
                    <XCircle size={12} className="text-accent-red" />
                  )}
                  <span className="text-text-secondary">
                    {results[agent.type].status} — {results[agent.type].turns}턴
                  </span>
                </div>
                <div className="text-text-muted max-h-32 overflow-y-auto whitespace-pre-wrap">
                  {results[agent.type].result || results[agent.type].error}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

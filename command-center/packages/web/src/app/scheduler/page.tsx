"use client";

import { useEffect, useState } from "react";
import { Calendar, Bot, Clock } from "lucide-react";

interface Job {
  id: string;
  name: string;
  cron: string;
  agent: string;
}

const AGENT_COLORS: Record<string, string> = {
  PRODUCTION: "text-accent-green",
  HR: "text-accent-purple",
  FINANCE: "text-accent-blue",
};

export default function SchedulerPage() {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    fetch("/api/scheduler")
      .then((r) => r.json())
      .then((data) => setJobs(data.jobs || []))
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <div className="bg-bg-secondary border border-border-primary rounded-lg">
        <div className="px-4 py-3 border-b border-border-primary flex items-center gap-2">
          <Calendar size={16} className="text-text-muted" />
          <span className="text-sm font-medium text-text-primary">
            스케줄러 작업 ({jobs.length})
          </span>
        </div>

        <div className="divide-y divide-border-primary">
          {jobs.map((job) => (
            <div
              key={job.id}
              className="px-4 py-3 flex items-center gap-4 hover:bg-bg-hover transition-colors"
            >
              <Bot
                size={16}
                className={AGENT_COLORS[job.agent] || "text-text-muted"}
              />
              <div className="flex-1">
                <div className="text-sm text-text-primary">{job.name}</div>
                <div className="text-xs text-text-muted">{job.agent} Agent</div>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-text-muted">
                <Clock size={12} />
                <code className="bg-bg-tertiary px-1.5 py-0.5 rounded">
                  {job.cron}
                </code>
              </div>
              <div className="w-2 h-2 rounded-full bg-accent-green" title="Active" />
            </div>
          ))}
        </div>
      </div>

      <div className="bg-bg-secondary border border-border-primary rounded-lg p-4">
        <h3 className="text-sm font-medium text-text-secondary mb-3">
          스케줄러 상태
        </h3>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold text-accent-green">
              {jobs.length}
            </div>
            <div className="text-xs text-text-muted">활성 작업</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-accent-blue">24/7</div>
            <div className="text-xs text-text-muted">자동 운영</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-text-primary">3</div>
            <div className="text-xs text-text-muted">에이전트 연결</div>
          </div>
        </div>
      </div>
    </div>
  );
}

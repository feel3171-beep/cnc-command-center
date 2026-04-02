export type TaskStatus = "INBOX" | "WIP" | "REVIEW" | "FINAL" | "ARCHIVE";
export type Priority = "P0" | "P1" | "P2" | "P3";
export type AgentType = "PRODUCTION" | "HR" | "FINANCE" | "COST";
export type PMRole = "FPA" | "HR_LEAD" | "PROD_LEAD" | "COST_LEAD";
export type ChatChannel = "staff" | "pm";

export interface Task {
  id: string;
  title: string;
  description?: string | null;
  status: TaskStatus;
  priority: Priority;
  projectId?: string | null;
  project?: Project | null;
  agentType?: AgentType | null;
  pmRole?: PMRole | null;
  pmName?: string | null;
  dueDate?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  tags: string[];
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
  outputs?: TaskOutput[];
  _count?: { chatMessages: number; outputs: number };
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  color: string;
}

export interface TaskOutput {
  id: string;
  taskId: string;
  filename: string;
  contentType: string;
  content: string;
  createdBy: string;
  createdAt: string;
}

export interface ChatMessage {
  id: string;
  taskId: string;
  channel: ChatChannel;
  role: "user" | "assistant" | "system";
  content: string;
  metadata?: Record<string, unknown> | null;
  createdAt: string;
}

export interface AgentRun {
  id: string;
  agentType: AgentType;
  trigger: string;
  taskId?: string | null;
  status: "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELLED";
  startedAt: string;
  completedAt?: string | null;
  turnsUsed: number;
  modelUsed?: string | null;
  totalTokens: number;
  resultSummary?: string | null;
  errorMessage?: string | null;
  toolCalls: Record<string, unknown>[];
}

export interface ScheduledJob {
  id: string;
  name: string;
  description?: string | null;
  cronExpression: string;
  agentType: AgentType;
  missionPrompt: string;
  status: "ACTIVE" | "PAUSED" | "COMPLETED" | "FAILED";
  slackChannel?: string | null;
  lastRunAt?: string | null;
  nextRunAt?: string | null;
  runCount: number;
}

export interface KPIData {
  date: string;
  total: {
    plan_qty: number;
    actual_qty: number;
    good_qty: number;
    loss_qty: number;
    achievement_rate: number;
    good_rate: number;
    order_cnt: number;
  };
  factories: FactoryKPI[];
}

export interface FactoryKPI {
  factory_code: string;
  factory_name: string;
  plan_qty: number;
  actual_qty: number;
  good_qty: number;
  loss_qty: number;
  achievement_rate: number;
  good_rate: number;
  order_cnt: number;
}

export const STATUS_LABELS: Record<TaskStatus, string> = {
  INBOX: "Inbox",
  WIP: "WIP",
  REVIEW: "Review",
  FINAL: "Final",
  ARCHIVE: "Archive",
};

export const PRIORITY_COLORS: Record<Priority, string> = {
  P0: "bg-priority-p0",
  P1: "bg-priority-p1",
  P2: "bg-priority-p2",
  P3: "bg-priority-p3",
};

export const AGENT_LABELS: Record<AgentType, string> = {
  PRODUCTION: "생산",
  HR: "인사",
  FINANCE: "재무",
  COST: "원가",
};

export const AGENT_COLORS: Record<AgentType, string> = {
  PRODUCTION: "text-accent-green",
  HR: "text-accent-purple",
  FINANCE: "text-accent-blue",
  COST: "text-accent-orange",
};

export const PM_ROLE_LABELS: Record<PMRole, string> = {
  FPA: "FP&A",
  HR_LEAD: "인사팀장",
  PROD_LEAD: "생산팀장",
  COST_LEAD: "원가팀장",
};

export const AGENT_PM_MAP: Record<AgentType, PMRole> = {
  FINANCE: "FPA",
  HR: "HR_LEAD",
  PRODUCTION: "PROD_LEAD",
  COST: "COST_LEAD",
};

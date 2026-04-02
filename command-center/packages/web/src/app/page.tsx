import { prisma } from "@/lib/prisma";
import { KPICards } from "@/components/dashboard/KPICards";
import { TaskSummary } from "@/components/dashboard/TaskSummary";
import { AgentStatus } from "@/components/dashboard/AgentStatus";
import { RecentActivity } from "@/components/dashboard/RecentActivity";

export const dynamic = "force-dynamic";

async function getStats() {
  try {
    const [taskCounts, recentRuns, recentTasks] = await Promise.all([
      prisma.task.groupBy({
        by: ["status"],
        _count: true,
        where: { isArchived: false },
      }),
      prisma.agentRun.findMany({
        orderBy: { startedAt: "desc" },
        take: 10,
      }),
      prisma.task.findMany({
        orderBy: { updatedAt: "desc" },
        take: 8,
        include: { project: true },
      }),
    ]);
    return { taskCounts, recentRuns, recentTasks };
  } catch {
    return { taskCounts: [], recentRuns: [], recentTasks: [] };
  }
}

export default async function DashboardPage() {
  const { taskCounts, recentRuns, recentTasks } = await getStats();

  const counts = Object.fromEntries(
    taskCounts.map((c: any) => [c.status, c._count])
  );

  const serializedRuns = JSON.parse(JSON.stringify(recentRuns));
  const serializedTasks = JSON.parse(JSON.stringify(recentTasks));

  return (
    <div className="space-y-6">
      <KPICards />

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-bg-secondary rounded-lg border border-border-primary p-4">
          <h3 className="text-sm font-medium text-text-secondary mb-3">
            태스크 현황
          </h3>
          <TaskSummary counts={counts} />
        </div>
        <div className="bg-bg-secondary rounded-lg border border-border-primary p-4">
          <h3 className="text-sm font-medium text-text-secondary mb-3">
            에이전트 상태
          </h3>
          <AgentStatus runs={serializedRuns} />
        </div>
        <div className="bg-bg-secondary rounded-lg border border-border-primary p-4">
          <h3 className="text-sm font-medium text-text-secondary mb-3">
            최근 활동
          </h3>
          <RecentActivity tasks={serializedTasks} />
        </div>
      </div>
    </div>
  );
}

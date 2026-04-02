import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import { TaskDetail } from "@/components/board/TaskDetail";
import { DualChatPanel } from "@/components/board/DualChatPanel";

export const dynamic = "force-dynamic";

export default async function TaskDetailPage({
  params,
}: {
  params: { taskId: string };
}) {
  let task: any = null;

  try {
    task = await prisma.task.findUnique({
      where: { id: params.taskId },
      include: {
        project: true,
        outputs: { orderBy: { createdAt: "desc" } },
        chatMessages: { orderBy: { createdAt: "asc" } },
        agentRuns: { orderBy: { startedAt: "desc" }, take: 5 },
      },
    });
  } catch {}

  if (!task) notFound();

  const serializedTask = JSON.parse(JSON.stringify(task));
  const staffMessages = task.chatMessages
    .filter((m: any) => m.channel === "staff")
    .map((m: any) => JSON.parse(JSON.stringify(m)));
  const pmMessages = task.chatMessages
    .filter((m: any) => m.channel === "pm")
    .map((m: any) => JSON.parse(JSON.stringify(m)));

  return (
    <div className="flex gap-4 h-[calc(100vh-8rem)]">
      <div className="flex-1 overflow-y-auto">
        <TaskDetail task={serializedTask} />
      </div>
      <div className="w-[420px] shrink-0">
        <DualChatPanel
          taskId={task.id}
          agentType={task.agentType}
          pmRole={task.pmRole}
          pmName={task.pmName}
          staffMessages={staffMessages}
          pmMessages={pmMessages}
        />
      </div>
    </div>
  );
}

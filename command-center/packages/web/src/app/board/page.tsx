import { prisma } from "@/lib/prisma";
import { KanbanBoard } from "@/components/board/KanbanBoard";
import type { TaskStatus } from "@/types/task";

export const dynamic = "force-dynamic";

const COLUMNS: TaskStatus[] = ["INBOX", "WIP", "REVIEW", "FINAL"];

export default async function BoardPage() {
  let tasks: any[] = [];
  let projects: any[] = [];

  try {
    tasks = await prisma.task.findMany({
      where: { isArchived: false },
      orderBy: [{ priority: "asc" }, { sortOrder: "asc" }],
      include: { project: true, _count: { select: { chatMessages: true, outputs: true } } },
    });
    projects = await prisma.project.findMany({ orderBy: { name: "asc" } });
  } catch {}

  const serialized = tasks.map((t) => ({
    ...t,
    dueDate: t.dueDate?.toISOString() ?? null,
    startedAt: t.startedAt?.toISOString() ?? null,
    completedAt: t.completedAt?.toISOString() ?? null,
    createdAt: t.createdAt.toISOString(),
    updatedAt: t.updatedAt.toISOString(),
    project: t.project
      ? { ...t.project, createdAt: undefined, updatedAt: undefined }
      : null,
  }));

  const columns = Object.fromEntries(
    COLUMNS.map((s) => [s, serialized.filter((t: any) => t.status === s)])
  );

  const serializedProjects = projects.map((p: any) => ({
    id: p.id,
    name: p.name,
    description: p.description,
    color: p.color,
  }));

  return <KanbanBoard columns={columns as any} projects={serializedProjects} />;
}

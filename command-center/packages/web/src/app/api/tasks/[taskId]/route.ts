import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(
  _req: NextRequest,
  { params }: { params: { taskId: string } }
) {
  const task = await prisma.task.findUnique({
    where: { id: params.taskId },
    include: {
      project: true,
      outputs: { orderBy: { createdAt: "desc" } },
      chatMessages: { orderBy: { createdAt: "asc" }, take: 50 },
      agentRuns: { orderBy: { startedAt: "desc" }, take: 5 },
    },
  });
  if (!task) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(task);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { taskId: string } }
) {
  const body = await req.json();
  const data: Record<string, unknown> = {};

  if (body.title !== undefined) data.title = body.title;
  if (body.description !== undefined) data.description = body.description;
  if (body.status !== undefined) {
    data.status = body.status;
    if (body.status === "WIP" && !body.startedAt) data.startedAt = new Date();
    if (body.status === "FINAL" || body.status === "ARCHIVE")
      data.completedAt = new Date();
  }
  if (body.priority !== undefined) data.priority = body.priority;
  if (body.projectId !== undefined) data.projectId = body.projectId || null;
  if (body.agentType !== undefined) data.agentType = body.agentType || null;
  if (body.dueDate !== undefined)
    data.dueDate = body.dueDate ? new Date(body.dueDate) : null;
  if (body.tags !== undefined) data.tags = body.tags;
  if (body.sortOrder !== undefined) data.sortOrder = body.sortOrder;
  if (body.isArchived !== undefined) data.isArchived = body.isArchived;

  const task = await prisma.task.update({
    where: { id: params.taskId },
    data,
    include: { project: true },
  });
  return NextResponse.json(task);
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { taskId: string } }
) {
  await prisma.task.update({
    where: { id: params.taskId },
    data: { isArchived: true },
  });
  return NextResponse.json({ ok: true });
}

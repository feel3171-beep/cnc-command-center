import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(req: NextRequest) {
  const status = req.nextUrl.searchParams.get("status");
  const tasks = await prisma.task.findMany({
    where: {
      isArchived: false,
      ...(status ? { status: status as any } : {}),
    },
    orderBy: [{ priority: "asc" }, { sortOrder: "asc" }, { createdAt: "desc" }],
    include: { project: true, _count: { select: { chatMessages: true, outputs: true } } },
  });
  return NextResponse.json(tasks);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const task = await prisma.task.create({
    data: {
      title: body.title,
      description: body.description || null,
      status: body.status || "INBOX",
      priority: body.priority || "P2",
      projectId: body.projectId || null,
      agentType: body.agentType || null,
      dueDate: body.dueDate ? new Date(body.dueDate) : null,
      tags: body.tags || [],
    },
    include: { project: true },
  });
  return NextResponse.json(task, { status: 201 });
}

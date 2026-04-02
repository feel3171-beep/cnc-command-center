import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { agentFetch } from "@/lib/api-client";

export async function GET(
  req: NextRequest,
  { params }: { params: { taskId: string } }
) {
  const channel = req.nextUrl.searchParams.get("channel") || undefined;
  const messages = await prisma.chatMessage.findMany({
    where: { taskId: params.taskId, ...(channel ? { channel } : {}) },
    orderBy: { createdAt: "asc" },
  });
  return NextResponse.json(messages);
}

export async function POST(req: NextRequest, { params }: { params: { taskId: string } }) {
  const { message, channel = "staff" } = await req.json();

  // Save user message with channel
  await prisma.chatMessage.create({
    data: { taskId: params.taskId, channel, role: "user", content: message },
  });

  // Get task context
  const task = await prisma.task.findUnique({
    where: { id: params.taskId },
    include: {
      project: true,
      outputs: { take: 3, orderBy: { createdAt: "desc" } },
      chatMessages: {
        where: { channel },
        take: 20,
        orderBy: { createdAt: "desc" },
      },
    },
  });

  // Build context with channel-specific system prompt addition
  const channelContext = channel === "pm"
    ? `\n\n[PM 모드] 이 대화는 PM(${task?.pmRole || "미배정"})과의 대화입니다. ` +
      `리뷰 피드백, 방향 설정, 전략적 판단에 집중하세요. ` +
      `실무 분석보다는 의사결정 지원에 초점을 맞추세요.`
    : `\n\n[Staff 모드] 이 대화는 실무 분석 대화입니다. ` +
      `데이터 조회, 분석 실행, Output 생성에 집중하세요.`;

  const agentRes = await agentFetch("/api/chat/stream", {
    method: "POST",
    body: JSON.stringify({
      message: message + channelContext,
      task_id: params.taskId,
      task_context: {
        title: task?.title,
        description: task?.description,
        agent_type: task?.agentType,
        pm_role: task?.pmRole,
        pm_name: task?.pmName,
        channel,
        project: task?.project?.name,
        recent_outputs: task?.outputs?.map((o) => ({
          filename: o.filename,
          content: o.content.slice(0, 2000),
        })),
        chat_history: task?.chatMessages
          ?.reverse()
          .slice(0, 10)
          .map((m) => ({ role: m.role, content: m.content.slice(0, 500) })),
      },
    }),
  });

  const stream = new ReadableStream({
    async start(controller) {
      const reader = agentRes.body?.getReader();
      if (!reader) {
        controller.close();
        return;
      }

      const decoder = new TextDecoder();
      let fullContent = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          controller.enqueue(new TextEncoder().encode(chunk));

          const lines = chunk.split("\n");
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === "text") fullContent += data.content;
              } catch {}
            }
          }
        }
      } finally {
        reader.releaseLock();
        if (fullContent) {
          await prisma.chatMessage.create({
            data: {
              taskId: params.taskId,
              channel,
              role: "assistant",
              content: fullContent,
            },
          });
        }
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

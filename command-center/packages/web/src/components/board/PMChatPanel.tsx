"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader } from "lucide-react";
import type { ChatMessage, AgentType, ChatChannel } from "@/types/task";

interface Props {
  taskId: string;
  initialMessages: ChatMessage[];
  agentType?: AgentType | null;
  channel: ChatChannel;
  accentColor: string;
  placeholder: string;
  emptyMessage: string;
}

export function PMChatPanel({
  taskId,
  initialMessages,
  agentType,
  channel,
  accentColor,
  placeholder,
  emptyMessage,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, streamText]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setStreaming(true);
    setStreamText("");

    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      taskId,
      channel,
      role: "user",
      content: text,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const res = await fetch(`/api/tasks/${taskId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, channel }),
      });

      if (!res.body) throw new Error("No stream");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let fullContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === "text") {
                fullContent += data.content;
                setStreamText(fullContent);
              } else if (data.type === "tool_use") {
                fullContent += `\n[${data.name}: ${data.description || "실행 중..."}]\n`;
                setStreamText(fullContent);
              }
            } catch {}
          }
        }
      }

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        taskId,
        channel,
        role: "assistant",
        content: fullContent,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setStreamText("");
    } catch {
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        taskId,
        channel,
        role: "assistant",
        content:
          "에이전트 서버에 연결할 수 없습니다. agent-server가 실행 중인지 확인하세요.",
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setStreaming(false);
    }
  };

  const isStaff = channel === "staff";
  const iconBg = isStaff ? "bg-accent-green/20" : "bg-accent-purple/20";
  const iconColor = isStaff ? "text-accent-green" : "text-accent-purple";
  const btnBg = isStaff ? "bg-accent-green" : "bg-accent-purple";
  const cursorColor = isStaff ? "bg-accent-green/60" : "bg-accent-purple/60";

  return (
    <div className="h-full flex flex-col bg-bg-secondary border-x border-b border-border-primary rounded-b-lg">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !streaming && (
          <div className="text-sm text-text-muted text-center py-8 whitespace-pre-line">
            {emptyMessage}
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className="flex gap-2">
            <div className="mt-0.5 shrink-0">
              {msg.role === "user" ? (
                <div className={`w-6 h-6 rounded-full ${isStaff ? "bg-accent-blue/20" : "bg-accent-purple/20"} flex items-center justify-center`}>
                  <User size={12} className={isStaff ? "text-accent-blue" : "text-accent-purple"} />
                </div>
              ) : (
                <div className={`w-6 h-6 rounded-full ${iconBg} flex items-center justify-center`}>
                  <Bot size={12} className={iconColor} />
                </div>
              )}
            </div>
            <div
              className={`text-sm leading-relaxed ${
                msg.role === "user" ? "text-text-primary" : "text-text-secondary"
              } whitespace-pre-wrap`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {streaming && streamText && (
          <div className="flex gap-2">
            <div className="mt-0.5 shrink-0">
              <div className={`w-6 h-6 rounded-full ${iconBg} flex items-center justify-center`}>
                <Bot size={12} className={iconColor} />
              </div>
            </div>
            <div className="text-sm text-text-secondary whitespace-pre-wrap">
              {streamText}
              <span className={`inline-block w-1.5 h-4 ${cursorColor} animate-pulse ml-0.5`} />
            </div>
          </div>
        )}

        {streaming && !streamText && (
          <div className="flex items-center gap-2 text-sm text-text-muted">
            <Loader size={14} className="animate-spin" />
            {isStaff ? "분석 중..." : "PM 검토 중..."}
          </div>
        )}
      </div>

      <div className="p-3 border-t border-border-primary">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
            placeholder={placeholder}
            disabled={streaming}
            className="flex-1 px-3 py-2 bg-bg-tertiary border border-border-primary rounded-md text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-blue disabled:opacity-50"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || streaming}
            className={`p-2 ${btnBg} text-black rounded-md hover:opacity-90 disabled:opacity-30 transition-opacity`}
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

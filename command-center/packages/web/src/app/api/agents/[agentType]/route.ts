import { NextRequest, NextResponse } from "next/server";
import { agentFetch } from "@/lib/api-client";

export async function POST(
  req: NextRequest,
  { params }: { params: { agentType: string } }
) {
  try {
    const body = await req.json();
    const res = await agentFetch(`/api/agents/${params.agentType}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { status: "FAILED", error: e.message },
      { status: 502 }
    );
  }
}

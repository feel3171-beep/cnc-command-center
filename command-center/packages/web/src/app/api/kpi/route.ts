import { NextResponse } from "next/server";
import { agentFetch } from "@/lib/api-client";

export async function GET() {
  try {
    const res = await agentFetch("/api/kpi/production/summary");
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(null, { status: 503 });
  }
}

const AGENT_URL = process.env.AGENT_SERVER_URL || "http://localhost:8000";

export async function agentFetch(path: string, init?: RequestInit) {
  const res = await fetch(`${AGENT_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`Agent server error: ${res.status}`);
  return res;
}

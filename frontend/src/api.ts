import type { Lead, LeadStatus } from "./types";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchLeads(status: LeadStatus): Promise<Lead[]> {
  const res = await fetch(`/api/leads?status=${status}`);
  return handleResponse<Lead[]>(res);
}

export async function patchStatus(
  username: string,
  status: LeadStatus
): Promise<void> {
  const res = await fetch(`/api/leads/${encodeURIComponent(username)}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  await handleResponse<unknown>(res);
}

export async function patchReply(
  username: string,
  reply: string
): Promise<void> {
  const res = await fetch(`/api/leads/${encodeURIComponent(username)}/reply`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reply }),
  });
  await handleResponse<unknown>(res);
}

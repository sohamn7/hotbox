export type LeadStatus = "inbox" | "sent" | "archive";

export interface Lead {
  username: string;
  full_name: string;
  raw_dm: string;
  score: number;
  summary: string;
  enrichment: Record<string, string | boolean | number>;
  status: LeadStatus;
  reply_text: string;
}

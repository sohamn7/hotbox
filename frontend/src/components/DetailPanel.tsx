import { useState } from "react";
import type { Lead } from "../types";
import ScoreBadge from "./ScoreBadge";

interface Props {
  lead: Lead | null;
  onSend: (username: string, reply: string) => Promise<void>;
  onDismiss: (username: string) => Promise<void>;
}

function EnrichmentRows({ enrichment }: { enrichment: Record<string, unknown> }) {
  const entries = Object.entries(enrichment).filter(([k]) => k !== "summary");
  if (entries.length === 0) return null;

  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
        Lead Profile
      </h3>
      <dl className="space-y-1">
        {entries.map(([key, value]) => {
          const display =
            typeof value === "boolean"
              ? value
                ? "Yes"
                : "No"
              : String(value);

          // Convert camelCase key to readable label
          const label = key
            .replace(/([A-Z])/g, " $1")
            .replace(/^./, (s) => s.toUpperCase());

          return (
            <div key={key} className="flex gap-2 text-sm">
              <dt className="text-gray-500 w-40 shrink-0">{label}</dt>
              <dd className="text-gray-900">{display}</dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}

export default function DetailPanel({ lead, onSend, onDismiss }: Props) {
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  if (!lead) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        Select a lead to view details.
      </div>
    );
  }

  async function handleSend() {
    if (!reply.trim() || !lead) return;
    setSending(true);
    try {
      await onSend(lead.username, reply.trim());
      setReply("");
    } finally {
      setSending(false);
    }
  }

  async function handleDismiss() {
    if (!lead) return;
    setDismissing(true);
    try {
      await onDismiss(lead.username);
    } finally {
      setDismissing(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200 bg-white shrink-0">
        <h2 className="text-xl font-semibold text-gray-900 flex-1">
          {lead.full_name || lead.username}
        </h2>
        <ScoreBadge score={lead.score} size="md" />
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* Message */}
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Message
          </h3>
          <blockquote className="border-l-4 border-gray-300 pl-4 text-sm text-gray-700 bg-gray-50 rounded-r py-3 pr-3 italic leading-relaxed">
            {lead.raw_dm}
          </blockquote>
        </section>

        {/* Summary */}
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Summary
          </h3>
          <p className="text-sm text-gray-700 leading-relaxed">{lead.summary}</p>
        </section>

        {/* Enrichment fields */}
        <EnrichmentRows enrichment={lead.enrichment} />
      </div>

      {/* Reply box — pinned to bottom */}
      <div className="px-6 py-4 border-t border-gray-200 bg-white shrink-0 space-y-3">
        <textarea
          value={reply}
          onChange={(e) => setReply(e.target.value)}
          placeholder="Write a reply..."
          rows={3}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <div className="flex gap-2">
          <button
            onClick={handleSend}
            disabled={sending || !reply.trim()}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium disabled:opacity-50 hover:bg-blue-700 transition-colors"
          >
            {sending ? "Sending..." : "Send"}
          </button>
          <button
            onClick={handleDismiss}
            disabled={dismissing}
            className="px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg font-medium disabled:opacity-50 hover:bg-gray-200 transition-colors"
          >
            {dismissing ? "Dismissing..." : "Dismiss"}
          </button>
        </div>
      </div>
    </div>
  );
}

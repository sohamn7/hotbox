import { useCallback, useEffect, useState } from "react";
import type { Lead, LeadStatus } from "./types";
import { fetchLeads, patchReply, patchStatus } from "./api";
import LeadList from "./components/LeadList";
import DetailPanel from "./components/DetailPanel";

type ViewCounts = Record<LeadStatus, number>;

const VIEWS: { label: string; status: LeadStatus }[] = [
  { label: "Inbox", status: "inbox" },
  { label: "Sent", status: "sent" },
  { label: "Archive", status: "archive" },
];

export default function App() {
  const [activeView, setActiveView] = useState<LeadStatus>("inbox");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [selected, setSelected] = useState<Lead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [counts, setCounts] = useState<ViewCounts>({ inbox: 0, sent: 0, archive: 0 });

  const loadLeads = useCallback(async (status: LeadStatus) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLeads(status);
      setLeads(data);
      setCounts((prev) => ({ ...prev, [status]: data.length }));
      // Clear selection if the selected lead is no longer in the list
      setSelected((prev) =>
        prev && data.some((l) => l.username === prev.username) ? prev : null
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load leads.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLeads(activeView);
  }, [activeView, loadLeads]);

  // Pre-fetch counts for all views on mount
  useEffect(() => {
    const views: LeadStatus[] = ["inbox", "sent", "archive"];
    views.forEach((v) => {
      fetchLeads(v)
        .then((data) => setCounts((prev) => ({ ...prev, [v]: data.length })))
        .catch(() => void 0);
    });
  }, []);

  async function handleSend(username: string, reply: string) {
    // Optimistic: remove from current view immediately
    setLeads((prev) => prev.filter((l) => l.username !== username));
    setSelected(null);
    setCounts((prev) => ({ ...prev, [activeView]: Math.max(0, prev[activeView] - 1) }));
    try {
      await patchReply(username, reply);
      setCounts((prev) => ({ ...prev, sent: prev.sent + 1 }));
    } catch {
      // Revert on error
      await loadLeads(activeView);
    }
  }

  async function handleDismiss(username: string) {
    setLeads((prev) => prev.filter((l) => l.username !== username));
    setSelected(null);
    setCounts((prev) => ({ ...prev, [activeView]: Math.max(0, prev[activeView] - 1) }));
    try {
      await patchStatus(username, "archive");
      setCounts((prev) => ({ ...prev, archive: prev.archive + 1 }));
    } catch {
      await loadLeads(activeView);
    }
  }

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Left nav */}
      <nav className="w-48 bg-white border-r border-gray-200 flex flex-col py-4 shrink-0">
        <div className="px-4 mb-6">
          <h1 className="text-lg font-bold text-gray-900">Hotbox</h1>
          <p className="text-xs text-gray-400">Lead triage</p>
        </div>
        <ul className="space-y-1 px-2">
          {VIEWS.map(({ label, status }) => {
            const active = activeView === status;
            return (
              <li key={status}>
                <button
                  onClick={() => {
                    setActiveView(status);
                    setSelected(null);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    active
                      ? "bg-blue-600 text-white"
                      : "text-gray-700 hover:bg-gray-100"
                  }`}
                >
                  <span>{label}</span>
                  {counts[status] > 0 && (
                    <span
                      className={`text-xs rounded-full px-2 py-0.5 font-semibold ${
                        active ? "bg-blue-500 text-white" : "bg-gray-200 text-gray-600"
                      }`}
                    >
                      {counts[status]}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Center: lead list */}
      <div className="w-72 bg-white border-r border-gray-200 flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700 capitalize">{activeView}</h2>
        </div>
        {loading && (
          <div className="px-4 py-3 text-xs text-gray-400">Loading...</div>
        )}
        {error && (
          <div className="px-4 py-3 text-xs text-red-500">{error}</div>
        )}
        {!loading && (
          <LeadList
            leads={leads}
            selectedUsername={selected?.username ?? null}
            onSelect={setSelected}
          />
        )}
      </div>

      {/* Right: detail panel */}
      <div className="flex-1 flex bg-white">
        <DetailPanel
          lead={selected}
          onSend={handleSend}
          onDismiss={handleDismiss}
        />
      </div>
    </div>
  );
}

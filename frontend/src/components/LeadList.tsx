import type { Lead } from "../types";
import ScoreBadge from "./ScoreBadge";

interface Props {
  leads: Lead[];
  selectedUsername: string | null;
  onSelect: (lead: Lead) => void;
}

export default function LeadList({ leads, selectedUsername, onSelect }: Props) {
  if (leads.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        No leads here.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
      {leads.map((lead) => {
        const isSelected = lead.username === selectedUsername;
        return (
          <button
            key={lead.username}
            onClick={() => onSelect(lead)}
            className={`w-full text-left px-4 py-3 transition-colors ${
              isSelected ? "bg-blue-50 border-l-4 border-blue-500" : "hover:bg-gray-50"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium text-gray-900 text-sm truncate pr-2">
                {lead.full_name || lead.username}
              </span>
              <ScoreBadge score={lead.score} />
            </div>
            <p className="text-xs text-gray-500 truncate">
              {lead.summary.slice(0, 80)}
            </p>
          </button>
        );
      })}
    </div>
  );
}

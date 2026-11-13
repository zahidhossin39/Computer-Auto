import React, { useMemo, useState } from "react";
import { Play, Search, ShieldAlert, Terminal, X } from "lucide-react";
import type { IntentCommand } from "../types";

interface CommandsViewProps {
  intents: IntentCommand[];
  onRunCommand: (text: string) => void;
}

const CATEGORIES = [
  "All",
  "Apps & Windows",
  "Browser & Web",
  "Media & System",
  "AI Vision",
] as const;

function normalizeCategory(raw: string): string {
  const lower = (raw || "").toLowerCase();
  if (lower.includes("app") || lower.includes("window")) {
    return "Apps & Windows";
  }
  if (lower.includes("browser") || lower.includes("web") || lower.includes("search")) {
    return "Browser & Web";
  }
  if (lower.includes("vision") || lower.includes("ai")) {
    return "AI Vision";
  }
  return "Media & System";
}

export const CommandsView: React.FC<CommandsViewProps> = ({
  intents,
  onRunCommand,
}) => {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("All");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return intents.filter((item) => {
      const cat = normalizeCategory(item.category);
      if (category !== "All" && cat !== category) return false;
      if (!q) return true;
      return (
        item.name.toLowerCase().includes(q) ||
        (item.description || "").toLowerCase().includes(q) ||
        item.phrases.some((p) => p.toLowerCase().includes(q))
      );
    });
  }, [intents, search, category]);

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5 max-w-5xl mx-auto w-full">
      {/* Search Bar & Category Filter Chips */}
      <div className="space-y-3.5">
        <div className="flex items-center gap-3 px-4 py-2.5 rounded-full bg-slate-100/90 dark:bg-[#1F1D26] border border-black/5 dark:border-white/[0.08] focus-within:border-[#D0BCFF] focus-within:ring-2 focus-within:ring-[#D0BCFF]/30 transition-all shadow-sm">
          <Search className="w-4 h-4 text-slate-400 dark:text-[#938F99]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search voice commands, hotkeys, or apps..."
            className="flex-1 bg-transparent text-sm text-slate-900 dark:text-[#E6E0E9] placeholder:text-slate-400 dark:placeholder:text-[#938F99] focus:outline-none py-0.5"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="p-1 rounded-full hover:bg-black/10 dark:hover:bg-white/10 text-slate-400"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <span className="text-xs font-mono font-semibold px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 text-slate-600 dark:text-[#CAC4D0]">
            {filtered.length} available
          </span>
        </div>

        {/* M3 Filter Chips */}
        <div className="flex flex-wrap items-center gap-2">
          {CATEGORIES.map((cat) => {
            const active = category === cat;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${
                  active
                    ? "bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] shadow-sm shadow-purple-500/20"
                    : "bg-slate-200/70 dark:bg-[#2B2833] text-slate-700 dark:text-[#CAC4D0] hover:bg-slate-300/70 dark:hover:bg-[#36333F] border border-black/5 dark:border-white/5"
                }`}
              >
                {cat}
              </button>
            );
          })}
        </div>
      </div>

      {/* M3 Command Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 pb-6">
        {filtered.map((cmd) => {
          const primaryPhrase = cmd.phrases[0] || cmd.name.replace(/_/g, " ");
          const displayCat = normalizeCategory(cmd.category);

          return (
            <div
              key={cmd.name}
              className="rounded-3xl bg-slate-100/90 dark:bg-[#1F1D26] border border-black/5 dark:border-white/[0.08] p-4 flex flex-col justify-between gap-3.5 hover:border-[#D0BCFF]/40 hover:bg-slate-200/50 dark:hover:bg-[#2A2733] transition-all shadow-sm group"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-7 h-7 rounded-full bg-[#D0BCFF]/15 flex items-center justify-center shrink-0">
                      <Terminal className="w-3.5 h-3.5 text-[#6750A4] dark:text-[#D0BCFF]" />
                    </div>
                    <span className="text-xs font-mono font-bold text-slate-900 dark:text-[#E6E0E9] truncate">
                      {cmd.name}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {cmd.destructive && (
                      <span
                        title="Requires guardrail confirmation"
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-300 border border-amber-500/30"
                      >
                        <ShieldAlert className="w-3 h-3" />
                        Guardrail
                      </span>
                    )}
                    <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-black/5 dark:bg-white/10 text-slate-600 dark:text-[#CAC4D0]">
                      {displayCat}
                    </span>
                  </div>
                </div>

                {cmd.description && (
                  <p className="text-xs text-slate-600 dark:text-[#CAC4D0] leading-relaxed pl-1">
                    {cmd.description}
                  </p>
                )}

                <div className="flex flex-wrap gap-1.5 pt-1 pl-1">
                  {cmd.phrases.slice(0, 3).map((phrase) => (
                    <span
                      key={phrase}
                      className="px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-slate-200/80 dark:bg-[#141218] text-slate-700 dark:text-[#D0BCFF] border border-black/5 dark:border-white/5"
                    >
                      "{phrase}"
                    </span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={() => onRunCommand(primaryPhrase)}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-full text-xs font-bold bg-[#D0BCFF]/15 hover:bg-[#6750A4] dark:hover:bg-[#D0BCFF] text-[#6750A4] dark:text-[#D0BCFF] hover:text-white dark:hover:text-[#381E72] border border-[#D0BCFF]/30 transition-all shadow-sm"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Run "{primaryPhrase}"</span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

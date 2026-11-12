import React, { useMemo, useState } from "react";
import { Play, Search, ShieldAlert, Terminal } from "lucide-react";
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
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
      {/* Search & Category Filter */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 px-3.5 py-2 rounded-2xl glass-panel focus-within:ring-2 focus-within:ring-sky-500/40">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search voice or text commands..."
            className="flex-1 bg-transparent text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none"
          />
          <span className="text-xs font-mono text-slate-400">
            {filtered.length} commands
          </span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((cat) => {
            const active = category === cat;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                  active
                    ? "bg-sky-500 text-white shadow-sm shadow-sky-500/25"
                    : "bg-slate-100 dark:bg-slate-900/70 text-slate-600 dark:text-slate-400 hover:bg-slate-200/70 dark:hover:bg-slate-800 border border-slate-200/70 dark:border-slate-800"
                }`}
              >
                {cat}
              </button>
            );
          })}
        </div>
      </div>

      {/* Command Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pb-4">
        {filtered.map((cmd) => {
          const primaryPhrase = cmd.phrases[0] || cmd.name.replace(/_/g, " ");
          const displayCat = normalizeCategory(cmd.category);

          return (
            <div
              key={cmd.name}
              className="rounded-2xl glass-card p-3.5 flex flex-col justify-between gap-3 hover:border-sky-500/40 transition-colors"
            >
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Terminal className="w-3.5 h-3.5 text-sky-500 shrink-0" />
                    <span className="text-xs font-mono font-semibold text-slate-800 dark:text-slate-200 truncate">
                      {cmd.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {cmd.destructive && (
                      <span
                        title="Requires guardrail confirmation"
                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-300"
                      >
                        <ShieldAlert className="w-3 h-3" />
                        Guardrail
                      </span>
                    )}
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-slate-200/70 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                      {displayCat}
                    </span>
                  </div>
                </div>

                {cmd.description && (
                  <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                    {cmd.description}
                  </p>
                )}

                <div className="flex flex-wrap gap-1 pt-1">
                  {cmd.phrases.slice(0, 3).map((phrase) => (
                    <span
                      key={phrase}
                      className="px-2 py-0.5 rounded-md text-[11px] font-mono bg-slate-100 dark:bg-slate-950/70 text-slate-700 dark:text-slate-300 border border-slate-200/70 dark:border-slate-800"
                    >
                      "{phrase}"
                    </span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={() => onRunCommand(primaryPhrase)}
                className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-semibold bg-sky-500/15 hover:bg-sky-500 text-sky-600 dark:text-sky-300 hover:text-white border border-sky-500/25 transition-all"
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
